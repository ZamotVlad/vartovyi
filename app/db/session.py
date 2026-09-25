from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import Settings


def create_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(
        settings.database_url,
        echo=settings.database_echo,
        # Відсіює з'єднання, які БД закрила, поки вони лежали в пулі
        pool_pre_ping=True,
    )


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    # expire_on_commit=False: після commit об'єкти лишаються читабельними
    # без неявного запиту, який в async-коді впав би з MissingGreenlet
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
