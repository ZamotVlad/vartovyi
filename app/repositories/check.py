import uuid
from collections import Counter, defaultdict
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import distinct_on

from app.db.models import Check
from app.domain.check import CheckStatus
from app.repositories.base import SqlRepository


class CheckRepository(SqlRepository):
    async def status_counts_since(
        self, monitor_ids: Sequence[uuid.UUID], since: datetime
    ) -> dict[uuid.UUID, Counter[CheckStatus]]:
        """Кількість перевірок кожного статусу за період, агреговано в БД.

        За 30 днів з інтервалом 30 с це ~86 тис. рядків на монітор: тягнути їх
        у Python заради трьох чисел було б марнотратно.
        """
        stmt = (
            select(Check.monitor_id, Check.status, func.count())
            .where(Check.monitor_id.in_(monitor_ids), Check.created_at >= since)
            .group_by(Check.monitor_id, Check.status)
        )
        counts: dict[uuid.UUID, Counter[CheckStatus]] = defaultdict(Counter)
        for monitor_id, status, count in await self.session.execute(stmt):
            counts[monitor_id][status] = count
        return counts

    async def latest_for_monitors(self, monitor_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, Check]:
        # DISTINCT ON - один запит замість N на кожен монітор
        stmt = (
            select(Check)
            .where(Check.monitor_id.in_(monitor_ids))
            .order_by(Check.monitor_id, Check.created_at.desc())
            .ext(distinct_on(Check.monitor_id))
        )
        result = await self.session.scalars(stmt)
        return {check.monitor_id: check for check in result}

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

    async def recent(self, monitor_id: uuid.UUID, limit: int) -> Sequence[Check]:
        """Останні limit перевірок у хронологічному порядку, найновіша остання."""
        stmt = (
            select(Check)
            .where(Check.monitor_id == monitor_id)
            .order_by(Check.created_at.desc())
            .limit(limit)
        )
        result = await self.session.scalars(stmt)
        return list(reversed(result.all()))

    async def count_for_monitor(self, monitor_id: uuid.UUID) -> int:
        stmt = select(func.count()).select_from(Check).where(Check.monitor_id == monitor_id)
        return await self.session.scalar(stmt) or 0

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
