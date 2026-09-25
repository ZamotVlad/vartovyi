import logging
import re
import time
import uuid

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.request_context import request_id_var
from app.schemas.common import ErrorDetail, ErrorResponse

logger = logging.getLogger("app.request")

REQUEST_ID_HEADER = "X-Request-ID"
TIMING_HEADER = "X-Process-Time-Ms"
# Вхідний id приймаємо лише безпечного вигляду: він потрапляє в логи і заголовки
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")

_INTERNAL_ERROR_BODY = (
    ErrorResponse(error=ErrorDetail(code="internal_error", message="Внутрішня помилка сервера"))
    .model_dump_json()
    .encode()
)


class RequestContextMiddleware:
    """Request id, час обробки, access-лог і перехоплення непійманих винятків.

    Чистий ASGI замість BaseHTTPMiddleware: той запускає ендпоінт в окремій
    задачі, що ламає contextvars і стрімінг відповідей.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = Headers(scope=scope).get(REQUEST_ID_HEADER)
        request_id = (
            incoming if incoming and _VALID_REQUEST_ID.match(incoming) else uuid.uuid4().hex
        )
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        status_code = 500
        response_started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code, response_started
            if message["type"] == "http.response.start":
                response_started = True
                status_code = message["status"]
                headers = MutableHeaders(scope=message)
                headers[REQUEST_ID_HEADER] = request_id
                headers[TIMING_HEADER] = f"{_elapsed_ms(started):.1f}"
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            logger.exception(
                "Unhandled exception", extra={"method": scope["method"], "path": scope["path"]}
            )
            if response_started:
                # Заголовки вже пішли клієнту, змінити статус неможливо
                raise
            await _send_internal_error(send_wrapper)
        finally:
            logger.info(
                "%s %s %s",
                scope["method"],
                scope["path"],
                status_code,
                extra={
                    "method": scope["method"],
                    "path": scope["path"],
                    "status_code": status_code,
                    "duration_ms": round(_elapsed_ms(started), 1),
                },
            )
            request_id_var.reset(token)


def _elapsed_ms(started: float) -> float:
    return (time.perf_counter() - started) * 1000


async def _send_internal_error(send: Send) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": 500,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(_INTERNAL_ERROR_BODY)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": _INTERNAL_ERROR_BODY})
