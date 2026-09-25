import logging
from collections.abc import Mapping
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.domain.errors import (
    AuthenticationError,
    ConflictError,
    DomainError,
    NotFoundError,
    PermissionDeniedError,
    RuleViolationError,
)
from app.schemas.common import ErrorDetail, ErrorResponse

logger = logging.getLogger(__name__)

# Категорія доменної помилки -> HTTP-статус. Єдине місце, де домен зустрічає HTTP
_STATUS_BY_CATEGORY: dict[type[DomainError], int] = {
    NotFoundError: status.HTTP_404_NOT_FOUND,
    ConflictError: status.HTTP_409_CONFLICT,
    AuthenticationError: status.HTTP_401_UNAUTHORIZED,
    PermissionDeniedError: status.HTTP_403_FORBIDDEN,
    RuleViolationError: status.HTTP_422_UNPROCESSABLE_CONTENT,
}

_BEARER_CHALLENGE = {"WWW-Authenticate": "Bearer"}

# Для документації: які відповіді-помилки може повернути будь-який захищений маршрут
ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    code: {"model": ErrorResponse}
    for code in (
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_403_FORBIDDEN,
        status.HTTP_404_NOT_FOUND,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
    )
}


def status_for(error: DomainError) -> int:
    for cls in type(error).__mro__:
        if cls in _STATUS_BY_CATEGORY:
            return _STATUS_BY_CATEGORY[cls]
    return status.HTTP_400_BAD_REQUEST


def _response(
    status_code: int,
    error: ErrorDetail,
    details: list[ErrorDetail] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    body = ErrorResponse(error=error, details=details)
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(exclude_none=True),
        headers=headers,
    )


async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    status_code = status_for(exc)
    headers = _BEARER_CHALLENGE if status_code == status.HTTP_401_UNAUTHORIZED else None
    return _response(status_code, ErrorDetail(code=exc.code, message=exc.detail), headers=headers)


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    details = [_validation_detail(err) for err in jsonable_encoder(exc.errors())]
    first = details[0] if details else None
    summary = ErrorDetail(
        code="validation_error",
        message=first.message if first else "Некоректні дані запиту",
        field=first.field if first else None,
    )
    return _response(status.HTTP_422_UNPROCESSABLE_CONTENT, summary, details)


async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    # Помилки маршрутизації Starlette (404 невідомий шлях, 405 метод) - в тому ж форматі
    phrase = HTTPStatus(exc.status_code).phrase
    code = phrase.lower().replace(" ", "_").replace("-", "_")
    message = exc.detail if isinstance(exc.detail, str) else phrase
    return _response(exc.status_code, ErrorDetail(code=code, message=message), headers=exc.headers)


def _validation_detail(err: dict[str, Any]) -> ErrorDetail:
    # loc виглядає як ("body", "interval_seconds") або ("query", "limit")
    location = [str(part) for part in err.get("loc", ())[1:]]
    message = str(err.get("msg", ""))
    # Pydantic додає префікс до повідомлень із власних валідаторів
    message = message.removeprefix("Value error, ")
    return ErrorDetail(
        code=str(err.get("type", "invalid")),
        message=message,
        field=".".join(location) or None,
    )


def register_exception_handlers(app: FastAPI) -> None:
    # Декоратор FastAPI приймає вузький тип винятку, add_exception_handler - ні
    app.exception_handler(DomainError)(domain_error_handler)
    app.exception_handler(RequestValidationError)(validation_error_handler)
    app.exception_handler(StarletteHTTPException)(http_error_handler)
