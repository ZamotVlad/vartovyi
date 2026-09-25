import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import CheckServiceDep, CurrentUserDep, HttpClientDep, MonitorServiceDep
from app.api.errors import ERROR_RESPONSES
from app.db.models import Check, Monitor
from app.schemas.check import CheckRead
from app.schemas.common import Page, PageParams
from app.schemas.monitor import (
    MonitorCreate,
    MonitorFilter,
    MonitorListItem,
    MonitorRead,
    MonitorUpdate,
)

router = APIRouter(prefix="/monitors", tags=["monitors"], responses=ERROR_RESPONSES)


@router.post("", response_model=MonitorRead, status_code=status.HTTP_201_CREATED)
async def create_monitor(
    data: MonitorCreate, user: CurrentUserDep, monitors: MonitorServiceDep
) -> Monitor:
    return await monitors.create(user, data)


@router.get("", response_model=Page[MonitorListItem])
async def list_monitors(
    params: Annotated[MonitorFilter, Query()], user: CurrentUserDep, monitors: MonitorServiceDep
) -> Page[MonitorListItem]:
    items, total = await monitors.list(user, params)
    return Page(
        items=items,
        total=total,
        limit=params.limit,
        offset=params.offset,
    )


@router.get("/{monitor_id}", response_model=MonitorRead)
async def get_monitor(
    monitor_id: uuid.UUID, user: CurrentUserDep, monitors: MonitorServiceDep
) -> Monitor:
    return await monitors.get(user, monitor_id)


@router.patch("/{monitor_id}", response_model=MonitorRead)
async def update_monitor(
    monitor_id: uuid.UUID, data: MonitorUpdate, user: CurrentUserDep, monitors: MonitorServiceDep
) -> Monitor:
    return await monitors.update(user, monitor_id, data)


@router.delete("/{monitor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_monitor(
    monitor_id: uuid.UUID, user: CurrentUserDep, monitors: MonitorServiceDep
) -> None:
    await monitors.delete(user, monitor_id)


@router.post(
    "/{monitor_id}/checks",
    response_model=CheckRead,
    status_code=status.HTTP_201_CREATED,
    summary="Перевірити зараз, поза розкладом",
)
async def run_check(
    monitor_id: uuid.UUID,
    user: CurrentUserDep,
    checks: CheckServiceDep,
    client: HttpClientDep,
) -> Check:
    return await checks.run_now(user, monitor_id, client)


@router.get("/{monitor_id}/checks", response_model=Page[CheckRead])
async def list_checks(
    monitor_id: uuid.UUID,
    params: Annotated[PageParams, Query()],
    user: CurrentUserDep,
    checks: CheckServiceDep,
) -> Page[CheckRead]:
    items, total = await checks.list_for_monitor(
        user, monitor_id, limit=params.limit, offset=params.offset
    )
    return Page(
        items=[CheckRead.model_validate(c) for c in items],
        total=total,
        limit=params.limit,
        offset=params.offset,
    )
