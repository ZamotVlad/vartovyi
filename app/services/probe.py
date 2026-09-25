import asyncio
import socket
import ssl
import time

import httpx

from app.domain.check import CheckTarget, FailureReason, ProbeResult


def classify_failure(exc: BaseException) -> FailureReason:
    """Переводить виняток транспорту в доменну причину, дивлячись у ланцюжок причин."""
    if isinstance(exc, TimeoutError | httpx.TimeoutException):
        return FailureReason.TIMEOUT
    for cause in _chain(exc):
        if isinstance(cause, socket.gaierror):
            return FailureReason.DNS_ERROR
        if isinstance(cause, ssl.SSLError):
            return FailureReason.TLS_ERROR
    return FailureReason.CONNECTION_ERROR


def _chain(exc: BaseException) -> list[BaseException]:
    seen: list[BaseException] = []
    current: BaseException | None = exc
    while current is not None and current not in seen:
        seen.append(current)
        current = current.__cause__ or current.__context__
    return seen


async def probe(
    client: httpx.AsyncClient, target: CheckTarget, *, timeout_s: float, body_max_bytes: int
) -> ProbeResult:
    """Одна перевірка. Мережеві збої повертаються як результат, а не як виняток.

    asyncio.timeout охоплює все: DNS, TLS, заголовки і читання тіла. Таймаути
    httpx діють на кожну фазу окремо і в сумі можуть перевищити бюджет.
    """
    started = time.perf_counter()
    try:
        async with asyncio.timeout(timeout_s):
            async with client.stream("GET", target.url) as response:
                snippet = None
                if target.expectation.keyword is not None:
                    snippet = await _read_prefix(response, body_max_bytes)
                return ProbeResult(
                    elapsed_ms=_elapsed_ms(started),
                    status_code=response.status_code,
                    body_snippet=snippet,
                )
    except (TimeoutError, httpx.TransportError) as exc:
        return ProbeResult(elapsed_ms=_elapsed_ms(started), failure=classify_failure(exc))


async def _read_prefix(response: httpx.Response, limit: int) -> str:
    # Читаємо не більше limit байт: сторінка на гігабайт не повинна з'їсти пам'ять
    chunks: list[bytes] = []
    size = 0
    async for chunk in response.aiter_bytes():
        chunks.append(chunk)
        size += len(chunk)
        if size >= limit:
            break
    return b"".join(chunks)[:limit].decode(response.encoding or "utf-8", errors="replace")


def _elapsed_ms(started: float) -> float:
    return (time.perf_counter() - started) * 1000
