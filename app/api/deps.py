from collections.abc import AsyncIterator
from typing import Annotated

import httpx
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader, OAuth2PasswordBearer
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings, get_settings
from app.db.models import User
from app.domain.errors import InvalidTokenError
from app.repositories.token_blacklist import TokenBlacklist
from app.services.api_key import ApiKeyService
from app.services.auth import AuthService
from app.services.check import CheckService
from app.services.monitor import MonitorService

SettingsDep = Annotated[Settings, Depends(get_settings)]


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Одна сесія на запит. Commit робить сервіс, rollback - тут при винятку."""
    sessionmaker: async_sessionmaker[AsyncSession] = request.app.state.sessionmaker
    async with sessionmaker() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_redis(request: Request) -> Redis:
    redis: Redis = request.app.state.redis
    return redis


RedisDep = Annotated[Redis, Depends(get_redis)]


def get_http_client(request: Request) -> httpx.AsyncClient:
    client: httpx.AsyncClient = request.app.state.http_client
    return client


HttpClientDep = Annotated[httpx.AsyncClient, Depends(get_http_client)]


def get_auth_service(session: SessionDep, redis: RedisDep, settings: SettingsDep) -> AuthService:
    return AuthService(session, TokenBlacklist(redis), settings)


def get_api_key_service(session: SessionDep) -> ApiKeyService:
    return ApiKeyService(session)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
ApiKeyServiceDep = Annotated[ApiKeyService, Depends(get_api_key_service)]

# auto_error=False: відсутність одного способу не помилка, якщо є інший
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{get_settings().api_v1_prefix}/auth/login", auto_error=False
)
api_key_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)

BearerTokenDep = Annotated[str | None, Depends(oauth2_scheme)]
ApiKeyHeaderDep = Annotated[str | None, Depends(api_key_scheme)]


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=InvalidTokenError.message,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    auth: AuthServiceDep, token: BearerTokenDep, api_key: ApiKeyHeaderDep
) -> User:
    """Користувач за Bearer-токеном або, для скриптів і CI, за X-API-Key."""
    try:
        if token is not None:
            return await auth.user_from_access_token(token)
        if api_key is not None:
            return await auth.user_from_api_key(api_key)
    except InvalidTokenError as exc:
        raise _unauthorized() from exc
    raise _unauthorized()


async def get_current_active_user(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Обліковий запис деактивовано"
        )
    return user


CurrentUserDep = Annotated[User, Depends(get_current_active_user)]


async def require_bearer_token(token: BearerTokenDep) -> str:
    if token is None:
        raise _unauthorized()
    return token


RequiredBearerTokenDep = Annotated[str, Depends(require_bearer_token)]


def get_monitor_service(session: SessionDep) -> MonitorService:
    return MonitorService(session)


MonitorServiceDep = Annotated[MonitorService, Depends(get_monitor_service)]


def get_check_service(session: SessionDep, settings: SettingsDep) -> CheckService:
    return CheckService(session, settings)


CheckServiceDep = Annotated[CheckService, Depends(get_check_service)]
