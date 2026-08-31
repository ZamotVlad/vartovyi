from typing import TypeVar

from pydantic import BaseModel, Field

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
    error: ErrorDetail
