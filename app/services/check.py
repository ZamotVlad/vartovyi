import logging
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.db.models import Check, Monitor, User
from app.domain.check import CheckTarget, Expectation, ProbeResult, evaluate
from app.domain.errors import MonitorNotFoundError
from app.domain.incident import IncidentAction, decide_incident_action
from app.repositories.check import CheckRepository
from app.repositories.incident import IncidentRepository
from app.repositories.monitor import MonitorRepository
from app.services.check_runner import run_probes

logger = logging.getLogger(__name__)


def to_target(monitor: Monitor) -> CheckTarget:
    return CheckTarget(
        monitor_id=monitor.id,
        url=monitor.url,
        timeout_ms=monitor.timeout_ms,
        expectation=Expectation(
            expected_status=monitor.expected_status,
            max_response_ms=monitor.max_response_ms,
            keyword=monitor.keyword,
        ),
    )


async def probe_targets(
    client: httpx.AsyncClient, targets: Sequence[CheckTarget], settings: Settings
) -> list[tuple[CheckTarget, ProbeResult]]:
    return await run_probes(
        client,
        targets,
        concurrency=settings.check_max_concurrency,
        max_timeout_s=settings.check_timeout_seconds,
        body_max_bytes=settings.check_body_max_bytes,
    )


class CheckService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.monitors = MonitorRepository(session)
        self.checks = CheckRepository(session)
        self.incidents = IncidentRepository(session)

    async def record(
        self, target: CheckTarget, probe: ProbeResult, checked_at: datetime
    ) -> Check | None:
        """Зберігає результат і оновлює інцидент. Commit робить викликач.

        None, якщо монітор видалили, поки йшла перевірка.
        """
        monitor = await self.monitors.get(target.monitor_id)
        if monitor is None:
            return None

        evaluation = evaluate(probe, target.expectation)
        check = await self.checks.add(
            Check(
                monitor_id=monitor.id,
                status=evaluation.status,
                elapsed_ms=probe.elapsed_ms,
                status_code=probe.status_code,
                failure=probe.failure,
                reason=evaluation.reason,
                created_at=checked_at,
            )
        )
        monitor.last_checked_at = checked_at
        await self._update_incident(monitor.id, checked_at)
        return check

    async def _update_incident(self, monitor_id: uuid.UUID, checked_at: datetime) -> None:
        threshold = self.settings.incident_failure_threshold
        recent = await self.checks.recent(monitor_id, limit=threshold)
        open_incident = await self.incidents.get_open(monitor_id)
        action = decide_incident_action(
            [c.status for c in recent],
            has_open_incident=open_incident is not None,
            failure_threshold=threshold,
        )
        if action is IncidentAction.OPEN:
            # Початок інциденту - перше падіння серії, а не момент, коли спрацював поріг
            await self.incidents.open(
                monitor_id, started_at=recent[0].created_at, reason=recent[-1].reason
            )
            logger.warning("Incident opened", extra={"monitor_id": str(monitor_id)})
        elif action is IncidentAction.RESOLVE and open_incident is not None:
            await self.incidents.resolve(open_incident, resolved_at=checked_at)
            logger.info("Incident resolved", extra={"monitor_id": str(monitor_id)})

    async def run_now(self, owner: User, monitor_id: uuid.UUID, client: httpx.AsyncClient) -> Check:
        """Позачергова перевірка одного монітора на запит користувача."""
        monitor = await self.monitors.get_for_owner(monitor_id, owner.id)
        if monitor is None:
            raise MonitorNotFoundError
        target = to_target(monitor)
        checked_at = datetime.now(UTC)
        results = await probe_targets(client, [target], self.settings)
        if not results:
            raise RuntimeError("Probe crashed, see logs")
        check = await self.record(target, results[0][1], checked_at)
        await self.session.commit()
        if check is None:
            raise MonitorNotFoundError
        return check

    async def list_for_monitor(
        self, owner: User, monitor_id: uuid.UUID, *, limit: int, offset: int
    ) -> tuple[Sequence[Check], int]:
        if await self.monitors.get_for_owner(monitor_id, owner.id) is None:
            raise MonitorNotFoundError
        items = await self.checks.list_for_monitor(monitor_id, limit=limit, offset=offset)
        return items, await self.checks.count_for_monitor(monitor_id)


async def run_due_checks(
    sessionmaker: async_sessionmaker[AsyncSession],
    client: httpx.AsyncClient,
    settings: Settings,
    *,
    now: datetime | None = None,
) -> int:
    """Один такт планувальника. Повертає кількість збережених перевірок.

    Сесія БД не тримається відкритою під час мережевих запитів: інакше
    повільні сайти займали б з'єднання з пулу на десятки секунд.
    """
    now = now or datetime.now(UTC)
    async with sessionmaker() as session:
        targets = [to_target(m) for m in await MonitorRepository(session).list_due(now)]
    if not targets:
        return 0

    results = await probe_targets(client, targets, settings)

    async with sessionmaker() as session:
        service = CheckService(session, settings)
        saved = 0
        for target, probe in results:
            try:
                # SAVEPOINT на кожен монітор: помилка одного не відкотить решту
                async with session.begin_nested():
                    if await service.record(target, probe, now) is not None:
                        saved += 1
            except Exception:
                logger.exception(
                    "Failed to record check", extra={"monitor_id": str(target.monitor_id)}
                )
        await session.commit()
    return saved
