import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Check, Monitor
from app.domain.check import CheckStatus
from app.repositories.monitor import MonitorRepository
from tests.factories import at, make_monitor


async def test_add_populates_server_defaults(db_session: AsyncSession) -> None:
    monitor = await MonitorRepository(db_session).add(make_monitor())

    assert isinstance(monitor.id, uuid.UUID)
    assert monitor.created_at is not None
    assert monitor.updated_at is not None
    assert monitor.is_active is True


async def test_get_returns_none_for_unknown_id(db_session: AsyncSession) -> None:
    assert await MonitorRepository(db_session).get(uuid.uuid4()) is None


async def test_list_page_paginates_newest_first(db_session: AsyncSession) -> None:
    repo = MonitorRepository(db_session)
    for minute in range(5):
        await repo.add(make_monitor(name=f"m{minute}", created_at=at(minute)))

    first, total = await repo.list_page(limit=2, offset=0)
    second, _ = await repo.list_page(limit=2, offset=2)

    assert total == 5
    assert [m.name for m in first] == ["m4", "m3"]
    assert [m.name for m in second] == ["m2", "m1"]


async def test_list_page_filter_applies_to_total(db_session: AsyncSession) -> None:
    repo = MonitorRepository(db_session)
    await repo.add(make_monitor(is_active=True))
    await repo.add(make_monitor(is_active=False))
    await repo.add(make_monitor(is_active=False))

    items, total = await repo.list_page(limit=10, offset=0, is_active=False)

    assert total == 2
    assert all(not m.is_active for m in items)


async def test_update_changes_only_given_fields(db_session: AsyncSession) -> None:
    repo = MonitorRepository(db_session)
    monitor = await repo.add(make_monitor(name="старе", interval_seconds=60))

    await repo.update(monitor, {"name": "нове"})
    db_session.expunge_all()
    reloaded = await repo.get(monitor.id)

    assert reloaded is not None
    assert reloaded.name == "нове"
    assert reloaded.interval_seconds == 60


async def test_delete_cascades_to_checks(db_session: AsyncSession) -> None:
    repo = MonitorRepository(db_session)
    monitor = await repo.add(make_monitor())
    db_session.add(Check(monitor_id=monitor.id, status=CheckStatus.UP, elapsed_ms=10))
    await db_session.flush()

    await repo.delete(monitor)

    assert await db_session.scalar(select(func.count()).select_from(Monitor)) == 0
    assert await db_session.scalar(select(func.count()).select_from(Check)) == 0


async def test_update_refreshes_updated_at_without_lazy_load(db_session: AsyncSession) -> None:
    repo = MonitorRepository(db_session)
    monitor = await repo.add(make_monitor())

    await repo.update(monitor, {"name": "нове"})

    # Серверне значення має бути вже завантажене: lazy load в async впав би
    assert monitor.updated_at is not None
