import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select

from app.db.models import Incident
from app.repositories.base import SqlRepository


class IncidentRepository(SqlRepository):
    async def get_open(self, monitor_id: uuid.UUID) -> Incident | None:
        stmt = select(Incident).where(
            Incident.monitor_id == monitor_id, Incident.resolved_at.is_(None)
        )
        return await self.session.scalar(stmt)

    async def open(
        self, monitor_id: uuid.UUID, *, started_at: datetime, reason: str | None
    ) -> Incident:
        incident = Incident(monitor_id=monitor_id, started_at=started_at, reason=reason)
        self.session.add(incident)
        await self.session.flush()
        return incident

    async def resolve(self, incident: Incident, *, resolved_at: datetime) -> Incident:
        incident.resolved_at = resolved_at
        await self.session.flush()
        return incident

    async def list_for_monitor(
        self, monitor_id: uuid.UUID, *, limit: int, offset: int = 0
    ) -> Sequence[Incident]:
        stmt = (
            select(Incident)
            .where(Incident.monitor_id == monitor_id)
            .order_by(Incident.started_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.scalars(stmt)
        return result.all()
