import asyncio
import os
from collections.abc import AsyncIterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

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
async def db_session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Сесія в зовнішній транзакції, що відкочується після тесту.

    commit у коді під тестом стає SAVEPOINT, тож тести ізольовані один від одного.
    """
    async with db_engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(
            bind=connection,
            expire_on_commit=False,
            autoflush=False,
            join_transaction_mode="create_savepoint",
        )
        try:
            yield session
        finally:
            await session.close()
            await transaction.rollback()
