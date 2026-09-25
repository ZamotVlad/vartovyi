import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CheckServiceDep, CurrentUserDep, HttpClientDep, MonitorServiceDep
from app.db.models import Check, Monitor
from app.domain.errors import InvalidMonitorConfigError, MonitorNotFoundError
from app.schemas.check import CheckRead
from app.schemas.common import Page, PageParams
from app.schemas.monitor import MonitorCreate, MonitorFilter, MonitorRead, MonitorUpdate

router = APIRouter(prefix="/monitors", tags=["monitors"])


@router.post("", response_model=MonitorRead, status_code=status.HTTP_201_CREATED)
async def create_monitor(
    data: MonitorCreate, user: CurrentUserDep, monitors: MonitorServiceDep
) -> Monitor:
    return await monitors.create(user, data)


@router.get("", response_model=Page[MonitorRead])
async def list_monitors(
    params: Annotated[MonitorFilter, Query()], user: CurrentUserDep, monitors: MonitorServiceDep
) -> Page[MonitorRead]:
    items, total = await monitors.list(user, params)
    return Page(
        items=[MonitorRead.model_validate(m) for m in items],
        total=total,
        limit=params.limit,
        offset=params.offset,
    )


@router.get("/{monitor_id}", response_model=MonitorRead)
async def get_monitor(
    monitor_id: uuid.UUID, user: CurrentUserDep, monitors: MonitorServiceDep
) -> Monitor:
    try:
        return await monitors.get(user, monitor_id)
    except MonitorNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, exc.detail) from exc


@router.patch("/{monitor_id}", response_model=MonitorRead)
async def update_monitor(
    monitor_id: uuid.UUID, data: MonitorUpdate, user: CurrentUserDep, monitors: MonitorServiceDep
) -> Monitor:
    try:
        return await monitors.update(user, monitor_id, data)
    except MonitorNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, exc.detail) from exc
    except InvalidMonitorConfigError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, exc.detail) from exc


@router.delete("/{monitor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_monitor(
    monitor_id: uuid.UUID, user: CurrentUserDep, monitors: MonitorServiceDep
) -> None:
    try:
        await monitors.delete(user, monitor_id)
    except MonitorNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, exc.detail) from exc


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
    try:
        return await checks.run_now(user, monitor_id, client)
    except MonitorNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, exc.detail) from exc


@router.get("/{monitor_id}/checks", response_model=Page[CheckRead])
async def list_checks(
    monitor_id: uuid.UUID,
    params: Annotated[PageParams, Query()],
    user: CurrentUserDep,
    checks: CheckServiceDep,
) -> Page[CheckRead]:
    try:
        items, total = await checks.list_for_monitor(
            user, monitor_id, limit=params.limit, offset=params.offset
        )
    except MonitorNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, exc.detail) from exc
    return Page(
        items=[CheckRead.model_validate(c) for c in items],
        total=total,
        limit=params.limit,
        offset=params.offset,
    )
