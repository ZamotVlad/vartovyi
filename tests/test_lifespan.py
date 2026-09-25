import httpx
from fastapi import Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.api.deps import get_http_client, get_redis, get_session
from app.config import Settings
from app.main import create_app
from tests.conftest import TEST_DATABASE_URL


async def test_lifespan_creates_and_closes_shared_resources(db_engine: AsyncEngine) -> None:
    settings = Settings(database_url=TEST_DATABASE_URL, scheduler_tick_seconds=60)
    app = create_app(settings)

    async with app.router.lifespan_context(app):
        request = Request({"type": "http", "app": app})
        client = get_http_client(request)
        assert isinstance(client, httpx.AsyncClient)
        assert not client.is_closed
        assert get_redis(request) is app.state.redis

        # Реальна залежність сесії працює поверх пулу, створеного в lifespan
        sessions = get_session(request)
        session = await anext(sessions)
        assert await session.scalar(text("select 1")) == 1
        await sessions.aclose()

    # Після shutdown клієнт закритий, а планувальник зупинений без помилок
    assert client.is_closed
