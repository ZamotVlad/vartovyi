from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.errors import StatusPageNotFoundError
from app.domain.uptime import UptimeSummary, summarize_counts
from app.repositories.check import CheckRepository
from app.repositories.monitor import MonitorRepository
from app.repositories.user import UserRepository
from app.schemas.check import MonitorStatusRead, StatusPageRead, UptimeRead

WINDOWS = {"24h": timedelta(hours=24), "7d": timedelta(days=7), "30d": timedelta(days=30)}


def _uptime(summary: UptimeSummary) -> UptimeRead:
    return UptimeRead(
        total=summary.total,
        up=summary.up,
        degraded=summary.degraded,
        down=summary.down,
        percent=summary.percent,
    )


class StatusPageService:
    def __init__(self, session: AsyncSession) -> None:
        self.users = UserRepository(session)
        self.monitors = MonitorRepository(session)
        self.checks = CheckRepository(session)

    async def get(self, slug: str, now: datetime | None = None) -> StatusPageRead:
        now = now or datetime.now(UTC)
        owner = await self.users.get_by_status_slug(slug)
        if owner is None or not owner.is_active:
            raise StatusPageNotFoundError

        monitors = await self.monitors.list_public(owner.id)
        ids = [m.id for m in monitors]
        latest = await self.checks.latest_for_monitors(ids) if ids else {}
        counts = {
            window: await self.checks.status_counts_since(ids, now - delta) if ids else {}
            for window, delta in WINDOWS.items()
        }

        items = []
        for monitor in monitors:
            last = latest.get(monitor.id)
            items.append(
                MonitorStatusRead(
                    name=monitor.name,
                    current_status=last.status if last else None,
                    last_checked_at=last.created_at if last else None,
                    uptime_24h=_uptime(summarize_counts(counts["24h"].get(monitor.id, {}))),
                    uptime_7d=_uptime(summarize_counts(counts["7d"].get(monitor.id, {}))),
                    uptime_30d=_uptime(summarize_counts(counts["30d"].get(monitor.id, {}))),
                )
            )
        return StatusPageRead(monitors=items, generated_at=now)
