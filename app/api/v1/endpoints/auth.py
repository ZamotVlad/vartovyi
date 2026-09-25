import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm

from app.api.deps import (
    ApiKeyServiceDep,
    AuthServiceDep,
    CurrentUserDep,
    RequiredBearerTokenDep,
)
from app.api.errors import ERROR_RESPONSES
from app.db.models import User
from app.schemas.auth import (
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyRead,
    RefreshRequest,
    TokenPair,
    UserCreate,
    UserRead,
)
from app.schemas.common import ErrorResponse

router = APIRouter(prefix="/auth", tags=["auth"], responses=ERROR_RESPONSES)


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    responses={status.HTTP_409_CONFLICT: {"model": ErrorResponse}},
)
async def register(data: UserCreate, auth: AuthServiceDep) -> User:
    return await auth.register(data)


@router.post("/login", response_model=TokenPair, summary="Логін (OAuth2 password flow)")
async def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()], auth: AuthServiceDep
) -> TokenPair:
    # OAuth2 називає поле username, у нас це email
    return await auth.login(form.username, form.password)


@router.post("/refresh", response_model=TokenPair)
async def refresh(data: RefreshRequest, auth: AuthServiceDep) -> TokenPair:
    return await auth.refresh(data.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    data: RefreshRequest, access_token: RequiredBearerTokenDep, auth: AuthServiceDep
) -> None:
    await auth.logout(access_token, data.refresh_token)


@router.get("/me", response_model=UserRead)
async def me(user: CurrentUserDep) -> User:
    return user


@router.post("/api-keys", response_model=ApiKeyCreated, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    data: ApiKeyCreate, user: CurrentUserDep, api_keys: ApiKeyServiceDep
) -> ApiKeyCreated:
    api_key, raw_key = await api_keys.create(user, data.name)
    return ApiKeyCreated(**ApiKeyRead.model_validate(api_key).model_dump(), key=raw_key)


@router.get("/api-keys", response_model=list[ApiKeyRead])
async def list_api_keys(user: CurrentUserDep, api_keys: ApiKeyServiceDep) -> list[ApiKeyRead]:
    return [ApiKeyRead.model_validate(k) for k in await api_keys.list_for_user(user)]


@router.delete("/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    key_id: uuid.UUID, user: CurrentUserDep, api_keys: ApiKeyServiceDep
) -> None:
    await api_keys.revoke(user, key_id)
