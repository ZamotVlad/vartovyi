from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Check, Monitor, User
from app.domain.check import CheckStatus, FailureReason
from app.repositories.check import CheckRepository
from app.repositories.monitor import MonitorRepository
from tests.factories import at, make_monitor


async def create_monitor(session: AsyncSession, owner: User) -> Monitor:
    return await MonitorRepository(session).add(make_monitor(owner.id))


async def test_enums_roundtrip_as_domain_types(db_session: AsyncSession, owner: User) -> None:
    monitor = await create_monitor(db_session, owner)
    repo = CheckRepository(db_session)
    await repo.add(
        Check(
            monitor_id=monitor.id,
            status=CheckStatus.DOWN,
            elapsed_ms=10_000,
            failure=FailureReason.TIMEOUT,
        )
    )
    db_session.expunge_all()

    latest = await repo.latest(monitor.id)

    assert latest is not None
    assert latest.status is CheckStatus.DOWN
    assert latest.failure is FailureReason.TIMEOUT


async def test_latest_returns_most_recent(db_session: AsyncSession, owner: User) -> None:
    monitor = await create_monitor(db_session, owner)
    repo = CheckRepository(db_session)
    await repo.add(
        Check(monitor_id=monitor.id, status=CheckStatus.DOWN, elapsed_ms=1, created_at=at(1))
    )
    await repo.add(
        Check(monitor_id=monitor.id, status=CheckStatus.UP, elapsed_ms=1, created_at=at(2))
    )

    latest = await repo.latest(monitor.id)

    assert latest is not None
    assert latest.status is CheckStatus.UP


async def test_latest_is_none_without_checks(db_session: AsyncSession, owner: User) -> None:
    monitor = await create_monitor(db_session, owner)
    assert await CheckRepository(db_session).latest(monitor.id) is None


async def test_statuses_since_is_chronological_and_windowed(
    db_session: AsyncSession, owner: User
) -> None:
    monitor = await create_monitor(db_session, owner)
    other = await create_monitor(db_session, owner)
    repo = CheckRepository(db_session)
    history = [
        (at(0), CheckStatus.DOWN),  # поза вікном
        (at(12), CheckStatus.DEGRADED),
        (at(10), CheckStatus.UP),
        (at(11), CheckStatus.DOWN),
    ]
    for created_at, status in history:
        await repo.add(
            Check(monitor_id=monitor.id, status=status, elapsed_ms=1, created_at=created_at)
        )
    await repo.add(
        Check(monitor_id=other.id, status=CheckStatus.DOWN, elapsed_ms=1, created_at=at(11))
    )

    statuses = await repo.statuses_since(monitor.id, at(10))

    assert list(statuses) == [CheckStatus.UP, CheckStatus.DOWN, CheckStatus.DEGRADED]


async def test_list_for_monitor_newest_first(db_session: AsyncSession, owner: User) -> None:
    monitor = await create_monitor(db_session, owner)
    repo = CheckRepository(db_session)
    for minute in range(3):
        await repo.add(
            Check(
                monitor_id=monitor.id,
                status=CheckStatus.UP,
                elapsed_ms=minute,
                created_at=at(minute),
            )
        )

    checks = await repo.list_for_monitor(monitor.id, limit=2)

    assert [c.elapsed_ms for c in checks] == [2, 1]
