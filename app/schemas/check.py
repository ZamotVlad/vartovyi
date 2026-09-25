from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.check import CheckStatus, FailureReason


class CheckRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    monitor_id: UUID
    status: CheckStatus
    elapsed_ms: float
    status_code: int | None
    failure: FailureReason | None
    reason: str | None
    created_at: datetime


class UptimeRead(BaseModel):
    total: int
    up: int
    degraded: int
    down: int
    percent: float | None = Field(
        description="Відсоток доступності. null, якщо перевірок ще не було"
    )


class MonitorStatusRead(BaseModel):
    """Публічна відповідь сторінки статусу. Без внутрішніх ідентифікаторів."""

    name: str
    current_status: CheckStatus | None
    last_checked_at: datetime | None
    uptime_24h: UptimeRead
    uptime_7d: UptimeRead
    uptime_30d: UptimeRead


class StatusPageRead(BaseModel):
    monitors: list[MonitorStatusRead]
    generated_at: datetime
