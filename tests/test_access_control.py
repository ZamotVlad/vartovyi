"""Систематична перевірка "хто НЕ має доступу" для всіх маршрутів застосунку.

Маршрути беруться з OpenAPI-схеми самого застосунку: захищені мають блок
security. Новий ендпоінт без захисту впаде тут, доки його свідомо не
додадуть до PUBLIC_ROUTES.
"""

import re
import uuid

import pytest
from httpx import AsyncClient

from app.main import create_app

PUBLIC_ROUTES = {
    ("GET", "/api/v1/health"),
    ("POST", "/api/v1/auth/register"),
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/refresh"),
    ("GET", "/api/v1/status/{slug}"),
}


def _operations() -> list[tuple[str, str, bool]]:
    schema = create_app().openapi()
    return [
        (method.upper(), path, bool(operation.get("security")))
        for path, item in schema["paths"].items()
        for method, operation in item.items()
    ]


PROTECTED = sorted((m, p) for m, p, secured in _operations() if secured)


def _concrete(path: str) -> str:
    return re.sub(r"\{[^}]+\}", str(uuid.uuid4()), path)


def test_every_route_is_either_protected_or_explicitly_public() -> None:
    unprotected = {(m, p) for m, p, secured in _operations() if not secured}
    assert unprotected == PUBLIC_ROUTES


def test_protected_routes_were_discovered() -> None:
    assert len(PROTECTED) >= 10


@pytest.mark.parametrize(("method", "path"), PROTECTED)
async def test_anonymous_request_is_rejected(client: AsyncClient, method: str, path: str) -> None:
    response = await client.request(method, _concrete(path), json={})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"


@pytest.mark.parametrize(("method", "path"), PROTECTED)
async def test_forged_credentials_are_rejected(client: AsyncClient, method: str, path: str) -> None:
    for headers in ({"Authorization": "Bearer forged"}, {"X-API-Key": "vtv_forged"}):
        response = await client.request(method, _concrete(path), json={}, headers=headers)
        assert response.status_code == 401, headers
