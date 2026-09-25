import uuid
from datetime import timedelta

import httpx
import pytest
import respx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.db.models import Monitor, User
from app.domain.check import CheckStatus, FailureReason, ProbeResult
from app.repositories.check import CheckRepository
from app.repositories.incident import IncidentRepository
from app.repositories.monitor import MonitorRepository
from app.services.check import CheckService, run_due_checks, to_target
from tests.factories import at, make_monitor

SETTINGS = Settings(incident_failure_threshold=2)
DOWN = ProbeResult(elapsed_ms=10, failure=FailureReason.CONNECTION_ERROR)
UP = ProbeResult(elapsed_ms=10, status_code=200)


@pytest.fixture
async def monitor(db_session: AsyncSession, owner: User) -> Monitor:
    return await MonitorRepository(db_session).add(make_monitor(owner.id))


async def record(session: AsyncSession, monitor: Monitor, probe: ProbeResult, minute: int) -> None:
    await CheckService(session, SETTINGS).record(to_target(monitor), probe, at(minute))
    await session.flush()


async def test_record_saves_evaluated_check(db_session: AsyncSession, monitor: Monitor) -> None:
    await record(db_session, monitor, ProbeResult(elapsed_ms=42, status_code=500), 0)

    check = await CheckRepository(db_session).latest(monitor.id)

    assert check is not None
    assert check.status is CheckStatus.DOWN
    assert check.status_code == 500
    assert check.reason is not None
    assert monitor.last_checked_at == at(0)


async def test_incident_opens_after_threshold_and_resolves(
    db_session: AsyncSession, monitor: Monitor
) -> None:
    incidents = IncidentRepository(db_session)

    await record(db_session, monitor, DOWN, 1)
    assert await incidents.get_open(monitor.id) is None

    await record(db_session, monitor, DOWN, 2)
    incident = await incidents.get_open(monitor.id)
    assert incident is not None
    assert incident.started_at == at(1)  # перше падіння серії

    await record(db_session, monitor, DOWN, 3)
    assert len(await incidents.list_for_monitor(monitor.id, limit=10)) == 1

    await record(db_session, monitor, UP, 4)
    assert await incidents.get_open(monitor.id) is None
    assert incident.resolved_at == at(4)


async def test_record_skips_deleted_monitor(db_session: AsyncSession) -> None:
    ghost = make_monitor(uuid.uuid4(), id=uuid.uuid4())
    result = await CheckService(db_session, SETTINGS).record(to_target(ghost), UP, at(0))
    assert result is None


@respx.mock
async def test_run_due_checks_selects_only_due_active_monitors(
    db_sessionmaker: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
    owner: User,
    http_client: httpx.AsyncClient,
) -> None:
    repo = MonitorRepository(db_session)
    now = at(30)
    never = await repo.add(make_monitor(owner.id, url="https://never.example.com"))
    overdue = await repo.add(
        make_monitor(
            owner.id, url="https://overdue.example.com", last_checked_at=now - timedelta(minutes=2)
        )
    )
    fresh = await repo.add(
        make_monitor(
            owner.id, url="https://fresh.example.com", last_checked_at=now - timedelta(seconds=10)
        )
    )
    paused = await repo.add(
        make_monitor(owner.id, url="https://paused.example.com", is_active=False)
    )
    await db_session.commit()
    route = respx.get(url__startswith="https://").respond(200)

    saved = await run_due_checks(db_sessionmaker, http_client, SETTINGS, now=now)

    assert saved == 2
    called = {call.request.url.host for call in route.calls}
    assert called == {"never.example.com", "overdue.example.com"}
    checks = CheckRepository(db_session)
    assert await checks.latest(never.id) is not None
    assert await checks.latest(overdue.id) is not None
    assert await checks.latest(fresh.id) is None
    assert await checks.latest(paused.id) is None


@respx.mock
async def test_run_due_checks_is_noop_without_due_monitors(
    db_sessionmaker: async_sessionmaker[AsyncSession], http_client: httpx.AsyncClient
) -> None:
    route = respx.get(url__startswith="https://").respond(200)

    assert await run_due_checks(db_sessionmaker, http_client, SETTINGS, now=at(0)) == 0
    assert not route.called
