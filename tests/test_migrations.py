import asyncio

from alembic import command
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.conftest import alembic_config


async def test_models_match_migrations(db_engine: AsyncEngine) -> None:
    # Падає, якщо модель змінили, а міграцію згенерувати забули
    await asyncio.to_thread(command.check, alembic_config())
