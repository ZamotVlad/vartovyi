from typing import Any

from httpx import AsyncClient

AUTH = "/api/v1/auth"
PASSWORD = "s3cret-passw0rd"


async def register(client: AsyncClient, email: str = "user@example.com") -> dict[str, Any]:
    response = await client.post(f"{AUTH}/register", json={"email": email, "password": PASSWORD})
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


async def login(client: AsyncClient, email: str = "user@example.com") -> dict[str, Any]:
    response = await client.post(f"{AUTH}/login", data={"username": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def auth_headers(client: AsyncClient, email: str = "user@example.com") -> dict[str, str]:
    await register(client, email)
    tokens = await login(client, email)
    return bearer(tokens["access_token"])
