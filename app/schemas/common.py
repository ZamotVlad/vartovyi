from typing import TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class Page[T](BaseModel):
    """Універсальна обгортка для списків. Одна на весь проєкт."""

    items: list[T]
    total: int = Field(description="Скільки записів усього, без урахування пагінації")
    limit: int
    offset: int


class ErrorDetail(BaseModel):
    code: str = Field(description="Машиночитаний код, наприклад monitor_not_found")
    message: str = Field(description="Людиночитане пояснення")
    field: str | None = Field(
        default=None, description="Поле, якщо помилка стосується конкретного поля"
    )


class ErrorResponse(BaseModel):
    """Єдиний формат тіла помилки для всього API."""

    error: ErrorDetail
    details: list[ErrorDetail] | None = Field(
        default=None, description="Усі помилки валідації, якщо їх кілька"
    )


class PageParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
