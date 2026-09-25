import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUserDep, MonitorServiceDep
from app.db.models import Monitor
from app.domain.errors import InvalidMonitorConfigError, MonitorNotFoundError
from app.schemas.common import Page
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
