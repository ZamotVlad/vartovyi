import json
import logging
from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.core.logging import JsonFormatter, RequestIdFilter
from app.core.request_context import get_request_id, request_id_var
from app.main import create_app

HEALTH = "/api/v1/health"


def build_app(**settings: object) -> FastAPI:
    app = create_app(Settings(**settings))  # type: ignore[arg-type]

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("secret internal detail")

    @app.get("/whoami")
    async def whoami() -> dict[str, str | None]:
        return {"request_id": get_request_id()}

    return app


@pytest.fixture
async def http() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=build_app(), raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def test_generates_request_id(http: AsyncClient) -> None:
    response = await http.get(HEALTH)
    assert len(response.headers["x-request-id"]) == 32


async def test_propagates_valid_incoming_request_id(http: AsyncClient) -> None:
    response = await http.get("/whoami", headers={"X-Request-ID": "trace-123"})

    assert response.headers["x-request-id"] == "trace-123"
    assert response.json() == {"request_id": "trace-123"}


@pytest.mark.parametrize("bad", ["a" * 129, "evil\tvalue", "<script>"])
async def test_replaces_unsafe_incoming_request_id(http: AsyncClient, bad: str) -> None:
    response = await http.get(HEALTH, headers={"X-Request-ID": bad})
    assert response.headers["x-request-id"] != bad


async def test_context_is_reset_after_request(http: AsyncClient) -> None:
    await http.get(HEALTH)
    assert request_id_var.get() is None


async def test_adds_timing_header(http: AsyncClient) -> None:
    response = await http.get(HEALTH)
    assert float(response.headers["x-process-time-ms"]) >= 0


async def test_unhandled_exception_becomes_uniform_500(
    http: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="app.request"):
        response = await http.get("/boom", headers={"X-Request-ID": "req-1"})

    assert response.status_code == 500
    assert response.json() == {
        "error": {"code": "internal_error", "message": "Внутрішня помилка сервера", "field": None}
    }
    assert "secret internal detail" not in response.text
    assert response.headers["x-request-id"] == "req-1"

    error_log = next(r for r in caplog.records if r.levelno == logging.ERROR)
    assert error_log.exc_info is not None
    access_log = next(r for r in caplog.records if getattr(r, "status_code", None) == 500)
    assert access_log.__dict__["path"] == "/boom"


async def test_access_log_has_request_fields(
    http: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="app.request"):
        await http.get(HEALTH)

    record = next(r for r in caplog.records if r.name == "app.request")
    assert record.__dict__["method"] == "GET"
    assert record.__dict__["status_code"] == 200
    assert record.__dict__["duration_ms"] >= 0


async def test_cors_allows_configured_origin() -> None:
    app = build_app(cors_origins=["https://status.example.com"])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        allowed = await client.options(
            HEALTH,
            headers={
                "Origin": "https://status.example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        denied = await client.get(HEALTH, headers={"Origin": "https://evil.example.com"})

    assert allowed.headers["access-control-allow-origin"] == "https://status.example.com"
    assert "access-control-allow-origin" not in denied.headers


async def test_cors_disabled_by_default(http: AsyncClient) -> None:
    response = await http.get(HEALTH, headers={"Origin": "https://status.example.com"})
    assert "access-control-allow-origin" not in response.headers


def test_json_formatter_includes_request_id_and_extra() -> None:
    record = logging.LogRecord("app.test", logging.INFO, __file__, 1, "hello %s", ("world",), None)
    record.path = "/x"
    token = request_id_var.set("req-42")
    try:
        RequestIdFilter().filter(record)
    finally:
        request_id_var.reset(token)

    payload = json.loads(JsonFormatter().format(record))

    assert payload["message"] == "hello world"
    assert payload["request_id"] == "req-42"
    assert payload["path"] == "/x"
    assert payload["level"] == "INFO"
