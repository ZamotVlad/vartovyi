import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Monitor, User
from app.domain.errors import InvalidMonitorConfigError, MonitorNotFoundError
from app.domain.monitor import MonitorTiming, timing_violation
from app.repositories.monitor import MonitorRepository
from app.schemas.monitor import MonitorCreate, MonitorFilter, MonitorUpdate


class MonitorService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.monitors = MonitorRepository(session)

    async def create(self, owner: User, data: MonitorCreate) -> Monitor:
        monitor = Monitor(owner_id=owner.id, **data.model_dump(exclude={"url"}), url=str(data.url))
        await self.monitors.add(monitor)
        await self.session.commit()
        return monitor

    async def get(self, owner: User, monitor_id: uuid.UUID) -> Monitor:
        monitor = await self.monitors.get_for_owner(monitor_id, owner.id)
        if monitor is None:
            # 404, а не 403: інакше відповідь підтверджувала б, що такий id існує
            raise MonitorNotFoundError
        return monitor

    async def list(self, owner: User, params: MonitorFilter) -> tuple[Sequence[Monitor], int]:
        return await self.monitors.list_page(
            owner.id,
            limit=params.limit,
            offset=params.offset,
            is_active=params.is_active,
            search=params.search,
            sort=params.sort,
        )

    async def update(self, owner: User, monitor_id: uuid.UUID, data: MonitorUpdate) -> Monitor:
        monitor = await self.get(owner, monitor_id)
        changes = data.model_dump(exclude_unset=True)
        if "url" in changes:
            changes["url"] = str(data.url)

        # Інваріанти перевіряються на об'єднаному стані: PATCH лише interval_seconds
        # може зламати сумісність з уже збереженим timeout_ms
        timing = MonitorTiming(
            interval_seconds=changes.get("interval_seconds", monitor.interval_seconds),
            timeout_ms=changes.get("timeout_ms", monitor.timeout_ms),
            max_response_ms=changes.get("max_response_ms", monitor.max_response_ms),
        )
        if violation := timing_violation(timing):
            raise InvalidMonitorConfigError(violation)

        await self.monitors.update(monitor, changes)
        await self.session.commit()
        return monitor

    async def delete(self, owner: User, monitor_id: uuid.UUID) -> None:
        monitor = await self.get(owner, monitor_id)
        await self.monitors.delete(monitor)
        await self.session.commit()
