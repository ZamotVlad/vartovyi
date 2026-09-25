import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import UnaryExpression, func, or_, select

from app.db.models import Monitor
from app.domain.monitor import MonitorSort
from app.repositories.base import SqlRepository

_ORDERING: dict[MonitorSort, tuple[UnaryExpression[Any], ...]] = {
    # id як другий ключ робить порядок стабільним між сторінками
    MonitorSort.CREATED_DESC: (Monitor.created_at.desc(), Monitor.id.asc()),
    MonitorSort.CREATED_ASC: (Monitor.created_at.asc(), Monitor.id.asc()),
    MonitorSort.NAME_ASC: (Monitor.name.asc(), Monitor.id.asc()),
    MonitorSort.NAME_DESC: (Monitor.name.desc(), Monitor.id.asc()),
}


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class MonitorRepository(SqlRepository):
    async def add(self, monitor: Monitor) -> Monitor:
        self.session.add(monitor)
        await self.session.flush()
        return monitor

    async def get(self, monitor_id: uuid.UUID) -> Monitor | None:
        return await self.session.get(Monitor, monitor_id)

    async def get_for_owner(self, monitor_id: uuid.UUID, owner_id: uuid.UUID) -> Monitor | None:
        # Власник у WHERE, а не перевірка після читання: чужий запис просто не існує
        stmt = select(Monitor).where(Monitor.id == monitor_id, Monitor.owner_id == owner_id)
        return await self.session.scalar(stmt)

    async def list_page(
        self,
        owner_id: uuid.UUID,
        *,
        limit: int,
        offset: int,
        is_active: bool | None = None,
        search: str | None = None,
        sort: MonitorSort = MonitorSort.CREATED_DESC,
    ) -> tuple[Sequence[Monitor], int]:
        """Сторінка моніторів власника і загальна кількість з тими ж фільтрами."""
        stmt = select(Monitor).where(Monitor.owner_id == owner_id)
        if is_active is not None:
            stmt = stmt.where(Monitor.is_active.is_(is_active))
        if search:
            pattern = f"%{_escape_like(search)}%"
            stmt = stmt.where(
                or_(
                    Monitor.name.ilike(pattern, escape="\\"),
                    Monitor.url.ilike(pattern, escape="\\"),
                )
            )

        total = await self.session.scalar(select(func.count()).select_from(stmt.subquery()))
        page = await self.session.scalars(
            stmt.order_by(*_ORDERING[sort]).limit(limit).offset(offset)
        )
        return page.all(), total or 0

    async def list_active(self) -> Sequence[Monitor]:
        result = await self.session.scalars(select(Monitor).where(Monitor.is_active.is_(True)))
        return result.all()

    async def update(self, monitor: Monitor, values: Mapping[str, Any]) -> Monitor:
        for field, value in values.items():
            setattr(monitor, field, value)
        await self.session.flush()
        return monitor

    async def delete(self, monitor: Monitor) -> None:
        await self.session.delete(monitor)
        await self.session.flush()
