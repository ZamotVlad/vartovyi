import asyncio
import os
from collections.abc import AsyncIterator

import httpx
import pytest
from alembic import command
from alembic.config import Config
from fakeredis.aioredis import FakeRedis
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.api.deps import get_http_client, get_redis, get_session
from app.core import security
from app.db.models import User
from app.main import create_app
from app.repositories.user import UserRepository
from tests.factories import make_user

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://vartovyi:vartovyi@localhost:5432/vartovyi_test",
)


def alembic_config() -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    return config


@pytest.fixture(scope="session")
async def db_engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    try:
        async with engine.connect():
            pass
    except OSError as exc:
        await engine.dispose()
        pytest.skip(f"Тестова БД недоступна ({TEST_DATABASE_URL}): {exc}")

    # Схему будують міграції, а не create_all: так тести перевіряють і їх
    config = alembic_config()
    # env.py сам запускає asyncio.run, тому виносимо його в окремий потік
    await asyncio.to_thread(command.downgrade, config, "base")
    await asyncio.to_thread(command.upgrade, config, "head")
    yield engine
    await asyncio.to_thread(command.downgrade, config, "base")
    await engine.dispose()


@pytest.fixture
async def db_connection(db_engine: AsyncEngine) -> AsyncIterator[AsyncConnection]:
    """З'єднання із зовнішньою транзакцією, що відкочується після тесту."""
    async with db_engine.connect() as connection:
        transaction = await connection.begin()
        try:
            yield connection
        finally:
            await transaction.rollback()


@pytest.fixture
def db_sessionmaker(db_connection: AsyncConnection) -> async_sessionmaker[AsyncSession]:
    # commit у коді під тестом стає SAVEPOINT, тож тести ізольовані один від одного
    return async_sessionmaker(
        bind=db_connection,
        expire_on_commit=False,
        autoflush=False,
        join_transaction_mode="create_savepoint",
    )


@pytest.fixture
async def db_session(
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with db_sessionmaker() as session:
        yield session


@pytest.fixture
async def owner(db_session: AsyncSession) -> User:
    return await UserRepository(db_session).add(make_user())


@pytest.fixture
async def redis() -> AsyncIterator[FakeRedis]:
    client = FakeRedis(decode_responses=True)
    try:
        yield client
    finally:
        await client.aclose()


@pytest.fixture
async def http_client() -> AsyncIterator[httpx.AsyncClient]:
    """Клієнт для перевірок. Зовнішні запити перехоплює respx у самих тестах."""
    async with httpx.AsyncClient(follow_redirects=True, timeout=None) as client:
        yield client


@pytest.fixture
async def client(
    db_session: AsyncSession, redis: FakeRedis, http_client: httpx.AsyncClient
) -> AsyncIterator[AsyncClient]:
    # ASGITransport не запускає lifespan, тож усю інфраструктуру підміняємо явно
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db_session
    app.dependency_overrides[get_redis] = lambda: redis
    app.dependency_overrides[get_http_client] = lambda: http_client
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http


@pytest.fixture(autouse=True, scope="session")
def fast_password_hashing() -> None:
    # Мінімальна вартість bcrypt: у тестах перевіряємо логіку, а не стійкість до перебору
    security._pwd_context.update(bcrypt__rounds=4)
