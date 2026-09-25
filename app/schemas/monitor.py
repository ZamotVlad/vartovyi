from datetime import datetime
from typing import Annotated, Self
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, model_validator

from app.domain.monitor import MonitorSort, MonitorTiming, timing_violation
from app.schemas.check import CheckRead
from app.schemas.common import PageParams

Name = Annotated[str, Field(min_length=1, max_length=100)]
IntervalSeconds = Annotated[int, Field(ge=30, le=86_400)]
TimeoutMs = Annotated[int, Field(ge=100, le=60_000)]
ResponseThresholdMs = Annotated[int, Field(ge=1, le=60_000)]
Keyword = Annotated[str, Field(min_length=1, max_length=200)]
HttpStatus = Annotated[int, Field(ge=100, le=599)]


class MonitorCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name
    url: AnyHttpUrl
    interval_seconds: IntervalSeconds = 60
    timeout_ms: TimeoutMs = 10_000
    expected_status: HttpStatus = 200
    max_response_ms: ResponseThresholdMs | None = None
    keyword: Keyword | None = None
    is_active: bool = True
    is_public: bool = False

    @model_validator(mode="after")
    def check_time_budget(self) -> Self:
        timing = MonitorTiming(self.interval_seconds, self.timeout_ms, self.max_response_ms)
        if violation := timing_violation(timing):
            raise ValueError(violation)
        return self


class MonitorUpdate(BaseModel):
    """Часткове оновлення. Усі поля необов'язкові."""

    model_config = ConfigDict(extra="forbid")

    name: Name | None = None
    url: AnyHttpUrl | None = None
    interval_seconds: IntervalSeconds | None = None
    timeout_ms: TimeoutMs | None = None
    expected_status: HttpStatus | None = None
    max_response_ms: ResponseThresholdMs | None = None
    keyword: Keyword | None = None
    is_active: bool | None = None
    is_public: bool | None = None

    @model_validator(mode="after")
    def forbid_null_for_required_fields(self) -> Self:
        # null дозволений лише там, де він має зміст "прибрати значення"
        nullable = {"max_response_ms", "keyword"}
        for field in self.model_fields_set - nullable:
            if getattr(self, field) is None:
                raise ValueError(f"Поле {field} не може бути null")
        return self


class MonitorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    url: str
    interval_seconds: int
    timeout_ms: int
    expected_status: int
    max_response_ms: int | None
    keyword: str | None
    is_active: bool
    is_public: bool
    last_checked_at: datetime | None
    created_at: datetime
    updated_at: datetime


class MonitorListItem(MonitorRead):
    """Рядок списку разом з останньою перевіркою: дашборду не треба N запитів."""

    latest_check: CheckRead | None = None


class MonitorFilter(PageParams):
    """Параметри списку. Використовується як Query-модель."""

    is_active: bool | None = None
    search: str | None = Field(
        default=None, min_length=1, max_length=100, description="Підрядок у назві або URL"
    )
    sort: MonitorSort = MonitorSort.CREATED_DESC
