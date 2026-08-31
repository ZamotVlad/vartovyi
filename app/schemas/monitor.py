from datetime import datetime
from typing import Annotated, Self
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, model_validator

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

    @model_validator(mode="after")
    def check_time_budget(self) -> Self:
        if self.timeout_ms > self.interval_seconds * 1000:
            raise ValueError(
                "timeout_ms не може перевищувати interval_seconds: "
                "перевірки почнуть накладатись одна на одну"
            )
        if self.max_response_ms is not None and self.max_response_ms > self.timeout_ms:
            raise ValueError(
                "max_response_ms не може перевищувати timeout_ms: "
                "поріг деградації недосяжний, з'єднання обірветься раніше"
            )
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
    created_at: datetime
    updated_at: datetime
