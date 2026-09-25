import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis

from app.api.middleware import REQUEST_ID_HEADER, TIMING_HEADER, RequestContextMiddleware
from app.api.v1.router import api_router
from app.config import Settings, get_settings
from app.core.logging import configure_logging
from app.db.session import create_engine, create_sessionmaker
from app.services.scheduler import run_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    configure_logging(settings.log_level, settings.log_format)
    engine = create_engine(settings)
    sessionmaker = create_sessionmaker(engine)
    app.state.sessionmaker = sessionmaker
    app.state.redis = Redis.from_url(settings.redis_url, decode_responses=True)
    # Один клієнт на весь процес: пул з'єднань і TLS-сесії перевикористовуються
    app.state.http_client = httpx.AsyncClient(
        follow_redirects=True,
        # Бюджет часу задає asyncio.timeout у probe, а не фазові таймаути httpx
        timeout=None,
        limits=httpx.Limits(max_connections=settings.check_max_concurrency),
        headers={"User-Agent": f"{settings.app_name}-monitor/0.1"},
    )
    scheduler = (
        asyncio.create_task(run_scheduler(sessionmaker, app.state.http_client, settings))
        if settings.scheduler_enabled
        else None
    )
    try:
        yield
    finally:
        if scheduler is not None:
            scheduler.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await scheduler
        await app.state.http_client.aclose()
        await app.state.redis.aclose()
        await engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    app = FastAPI(
        title=settings.app_name,
        description="Сервіс моніторингу доступності сайтів та API",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    # Останній доданий middleware - зовнішній. CORS зовні, щоб навіть
    # відповідь 500 від RequestContextMiddleware отримала CORS-заголовки
    app.add_middleware(RequestContextMiddleware)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=[REQUEST_ID_HEADER, TIMING_HEADER],
        )
    return app


app = create_app()
