import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import func, select

from app.db.models import Monitor
from app.repositories.base import SqlRepository


class MonitorRepository(SqlRepository):
    async def add(self, monitor: Monitor) -> Monitor:
        self.session.add(monitor)
        await self.session.flush()
        return monitor

    async def get(self, monitor_id: uuid.UUID) -> Monitor | None:
        return await self.session.get(Monitor, monitor_id)

    async def list_page(
        self, *, limit: int, offset: int, is_active: bool | None = None
    ) -> tuple[Sequence[Monitor], int]:
        """Сторінка моніторів і загальна кількість з тими ж фільтрами."""
        stmt = select(Monitor)
        if is_active is not None:
            stmt = stmt.where(Monitor.is_active.is_(is_active))

        total = await self.session.scalar(select(func.count()).select_from(stmt.subquery()))
        page = await self.session.scalars(
            stmt.order_by(Monitor.created_at.desc(), Monitor.id).limit(limit).offset(offset)
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
