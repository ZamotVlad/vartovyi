import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select

from app.db.models import Check
from app.domain.check import CheckStatus
from app.repositories.base import SqlRepository


class CheckRepository(SqlRepository):
    async def add(self, check: Check) -> Check:
        self.session.add(check)
        await self.session.flush()
        return check

    async def latest(self, monitor_id: uuid.UUID) -> Check | None:
        stmt = (
            select(Check)
            .where(Check.monitor_id == monitor_id)
            .order_by(Check.created_at.desc())
            .limit(1)
        )
        return await self.session.scalar(stmt)

    async def list_for_monitor(
        self, monitor_id: uuid.UUID, *, limit: int, offset: int = 0
    ) -> Sequence[Check]:
        stmt = (
            select(Check)
            .where(Check.monitor_id == monitor_id)
            .order_by(Check.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.scalars(stmt)
        return result.all()

    async def statuses_since(self, monitor_id: uuid.UUID, since: datetime) -> Sequence[CheckStatus]:
        """Тільки статуси в хронологічному порядку - вхід для app.domain.uptime."""
        stmt = (
            select(Check.status)
            .where(Check.monitor_id == monitor_id, Check.created_at >= since)
            .order_by(Check.created_at)
        )
        result = await self.session.scalars(stmt)
        return result.all()
