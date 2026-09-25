import asyncio
import logging
from collections.abc import Sequence

import httpx

from app.domain.check import CheckTarget, ProbeResult
from app.services.probe import probe

logger = logging.getLogger(__name__)


async def run_probes(
    client: httpx.AsyncClient,
    targets: Sequence[CheckTarget],
    *,
    concurrency: int,
    max_timeout_s: float,
    body_max_bytes: int,
) -> list[tuple[CheckTarget, ProbeResult]]:
    """Паралельно перевіряє цілі, не більше concurrency одночасно.

    Семафор обмежує кількість відкритих з'єднань і сокетів: 5000 моніторів
    не повинні означати 5000 одночасних TLS-рукостискань.
    """
    semaphore = asyncio.Semaphore(concurrency)
    results: list[tuple[CheckTarget, ProbeResult]] = []

    async def run_one(target: CheckTarget) -> None:
        async with semaphore:
            timeout_s = min(target.timeout_ms / 1000, max_timeout_s)
            try:
                result = await probe(
                    client, target, timeout_s=timeout_s, body_max_bytes=body_max_bytes
                )
            except Exception:
                # Баг в одній перевірці не повинен скасувати решту задач TaskGroup
                logger.exception("Probe crashed", extra={"monitor_id": str(target.monitor_id)})
                return
            results.append((target, result))

    async with asyncio.TaskGroup() as group:
        for target in targets:
            group.create_task(run_one(target))
    return results
