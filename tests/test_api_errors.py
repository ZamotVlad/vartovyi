from typing import Any

import pytest
from httpx import AsyncClient

from app.api.errors import status_for
from app.domain.errors import (
    DomainError,
    EmailAlreadyRegisteredError,
    InactiveUserError,
    InvalidMonitorConfigError,
    InvalidTokenError,
    MonitorNotFoundError,
)
from app.main import create_app
from tests.helpers import AUTH, PASSWORD, auth_headers, register

MONITORS = "/api/v1/monitors"


def assert_error_shape(body: dict[str, Any], code: str) -> None:
    assert set(body) <= {"error", "details"}
    assert body["error"]["code"] == code
    assert isinstance(body["error"]["message"], str)
    assert body["error"]["message"]


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (MonitorNotFoundError(), 404),
        (EmailAlreadyRegisteredError(), 409),
        (InvalidTokenError(), 401),
        (InactiveUserError(), 403),
        (InvalidMonitorConfigError("x"), 422),
        (DomainError(), 400),
    ],
)
def test_status_is_derived_from_error_category(error: DomainError, status: int) -> None:
    assert status_for(error) == status


def test_domain_error_keeps_custom_message() -> None:
    assert InvalidMonitorConfigError("деталі").detail == "деталі"
    assert MonitorNotFoundError().detail == MonitorNotFoundError.message


async def test_domain_not_found(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    missing = "00000000-0000-0000-0000-000000000000"

    response = await client.get(f"{MONITORS}/{missing}", headers=headers)

    assert response.status_code == 404
    assert_error_shape(response.json(), "monitor_not_found")


async def test_domain_conflict(client: AsyncClient) -> None:
    await register(client)
    response = await client.post(
        f"{AUTH}/register", json={"email": "user@example.com", "password": PASSWORD}
    )
    assert response.status_code == 409
    assert_error_shape(response.json(), "email_already_registered")


async def test_authentication_errors_carry_bearer_challenge(client: AsyncClient) -> None:
    missing = await client.get(f"{AUTH}/me")
    invalid = await client.get(f"{AUTH}/me", headers={"Authorization": "Bearer nope"})

    assert_error_shape(missing.json(), "not_authenticated")
    assert_error_shape(invalid.json(), "invalid_token")
    assert missing.headers["www-authenticate"] == "Bearer"
    assert invalid.headers["www-authenticate"] == "Bearer"


async def test_rule_violation_from_service(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    created = await client.post(
        MONITORS,
        json={"name": "s", "url": "https://example.com", "timeout_ms": 45_000},
        headers=headers,
    )
    response = await client.patch(
        f"{MONITORS}/{created.json()['id']}", json={"interval_seconds": 30}, headers=headers
    )

    assert response.status_code == 422
    body = response.json()
    assert_error_shape(body, "invalid_monitor_config")
    assert "накладатись" in body["error"]["message"]


async def test_request_validation_lists_every_field(client: AsyncClient) -> None:
    headers = await auth_headers(client)

    response = await client.post(
        MONITORS, json={"name": "", "url": "ftp://x", "interval_seconds": 1}, headers=headers
    )

    assert response.status_code == 422
    body = response.json()
    assert_error_shape(body, "validation_error")
    fields = {d["field"] for d in body["details"]}
    assert {"name", "url", "interval_seconds"} <= fields
    assert body["error"]["field"] in fields


async def test_model_validator_message_has_no_pydantic_prefix(client: AsyncClient) -> None:
    headers = await auth_headers(client)

    response = await client.post(
        MONITORS,
        json={
            "name": "s",
            "url": "https://example.com",
            "interval_seconds": 30,
            "timeout_ms": 45_000,
        },
        headers=headers,
    )

    message = response.json()["error"]["message"]
    assert message.startswith("timeout_ms")
    assert response.json()["error"].get("field") is None


async def test_query_validation_names_parameter(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    response = await client.get(MONITORS, params={"limit": 0}, headers=headers)
    assert response.json()["error"]["field"] == "limit"


async def test_unknown_route_uses_same_format(client: AsyncClient) -> None:
    response = await client.get("/api/v1/nope")
    assert response.status_code == 404
    assert_error_shape(response.json(), "not_found")


async def test_wrong_method_uses_same_format(client: AsyncClient) -> None:
    response = await client.put("/api/v1/health")
    assert response.status_code == 405
    assert_error_shape(response.json(), "method_not_allowed")


def test_openapi_documents_error_schema() -> None:
    schema = create_app().openapi()
    get_monitor = schema["paths"]["/api/v1/monitors/{monitor_id}"]["get"]
    ref = get_monitor["responses"]["404"]["content"]["application/json"]["schema"]["$ref"]
    assert ref.endswith("/ErrorResponse")
