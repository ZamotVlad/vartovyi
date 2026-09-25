import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Incident, User
from app.repositories.incident import IncidentRepository
from app.repositories.monitor import MonitorRepository
from tests.factories import at, make_monitor


async def test_open_then_resolve(db_session: AsyncSession, owner: User) -> None:
    monitor = await MonitorRepository(db_session).add(make_monitor(owner.id))
    repo = IncidentRepository(db_session)

    incident = await repo.open(monitor.id, started_at=at(0), reason="Очікували 200")
    assert incident.is_open
    assert await repo.get_open(monitor.id) == incident

    await repo.resolve(incident, resolved_at=at(5))

    assert not incident.is_open
    assert await repo.get_open(monitor.id) is None


async def test_second_open_incident_is_rejected_by_db(
    db_session: AsyncSession, owner: User
) -> None:
    monitor = await MonitorRepository(db_session).add(make_monitor(owner.id))
    repo = IncidentRepository(db_session)
    await repo.open(monitor.id, started_at=at(0), reason=None)

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(Incident(monitor_id=monitor.id, started_at=at(1)))


async def test_new_incident_allowed_after_resolve(db_session: AsyncSession, owner: User) -> None:
    monitor = await MonitorRepository(db_session).add(make_monitor(owner.id))
    repo = IncidentRepository(db_session)
    first = await repo.open(monitor.id, started_at=at(0), reason=None)
    await repo.resolve(first, resolved_at=at(5))

    await repo.open(monitor.id, started_at=at(10), reason=None)

    incidents = await repo.list_for_monitor(monitor.id, limit=10)
    assert [i.started_at for i in incidents] == [at(10), at(0)]
