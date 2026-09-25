import asyncio
import logging

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.services.check import run_due_checks

logger = logging.getLogger(__name__)


async def run_scheduler(
    sessionmaker: async_sessionmaker[AsyncSession],
    client: httpx.AsyncClient,
    settings: Settings,
) -> None:
    """Нескінченний цикл тактів. Зупиняється скасуванням задачі в lifespan.

    Такти йдуть послідовно, тож один монітор ніколи не перевіряється двічі
    паралельно в межах процесу.
    """
    logger.info("Scheduler started", extra={"tick_seconds": settings.scheduler_tick_seconds})
    while True:
        try:
            saved = await run_due_checks(sessionmaker, client, settings)
            if saved:
                logger.info("Checks recorded", extra={"count": saved})
        except Exception:
            # Недоступна БД не повинна вбивати планувальник назавжди
            logger.exception("Scheduler tick failed")
        await asyncio.sleep(settings.scheduler_tick_seconds)
