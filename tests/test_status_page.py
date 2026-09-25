from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Check, User
from app.domain.check import CheckStatus
from app.repositories.check import CheckRepository
from tests.helpers import AUTH, auth_headers
from tests.test_api_monitors import MONITORS, create

STATUS_API = "/api/v1/status"


async def set_slug(client: AsyncClient, headers: dict[str, str], slug: str | None) -> Any:
    return await client.patch(f"{AUTH}/me", json={"status_slug": slug}, headers=headers)


async def add_checks(
    session: AsyncSession, monitor_id: str, statuses: list[tuple[timedelta, CheckStatus]]
) -> None:
    repo = CheckRepository(session)
    now = datetime.now(UTC)
    for age, status in statuses:
        await repo.add(
            Check(monitor_id=monitor_id, status=status, elapsed_ms=1, created_at=now - age)
        )


@pytest.fixture
async def alice(client: AsyncClient) -> dict[str, str]:
    headers = await auth_headers(client, "alice@example.com")
    assert (await set_slug(client, headers, "alice-co")).status_code == 200
    return headers


# налаштування адреси сторінки


async def test_slug_is_saved_and_can_be_cleared(client: AsyncClient) -> None:
    headers = await auth_headers(client)

    saved = await set_slug(client, headers, "my-status")
    cleared = await set_slug(client, headers, None)

    assert saved.json()["status_slug"] == "my-status"
    assert cleared.json()["status_slug"] is None


@pytest.mark.parametrize("slug", ["ab", "Upper", "-dash", "dash-", "space here", "x" * 51])
async def test_invalid_slug_is_rejected(client: AsyncClient, slug: str) -> None:
    headers = await auth_headers(client)
    assert (await set_slug(client, headers, slug)).status_code == 422


async def test_slug_must_be_unique(client: AsyncClient, alice: dict[str, str]) -> None:
    bob = await auth_headers(client, "bob@example.com")

    response = await set_slug(client, bob, "alice-co")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "status_slug_taken"


async def test_resaving_own_slug_is_allowed(client: AsyncClient, alice: dict[str, str]) -> None:
    assert (await set_slug(client, alice, "alice-co")).status_code == 200


# публічний API


async def test_shows_only_public_monitors_without_internal_data(
    client: AsyncClient, alice: dict[str, str]
) -> None:
    await create(client, alice, name="API", url="https://internal.example.com", is_public=True)
    await create(client, alice, name="Приватний", is_public=False)

    response = await client.get(f"{STATUS_API}/alice-co")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=30"
    monitors = response.json()["monitors"]
    assert [m["name"] for m in monitors] == ["API"]
    assert "id" not in monitors[0]
    assert "url" not in monitors[0]
    assert "internal.example.com" not in response.text


async def test_does_not_leak_other_users_monitors(
    client: AsyncClient, alice: dict[str, str]
) -> None:
    bob = await auth_headers(client, "bob@example.com")
    await create(client, bob, name="Bob public", is_public=True)

    response = await client.get(f"{STATUS_API}/alice-co")

    assert response.json()["monitors"] == []


async def test_uptime_windows_and_current_status(
    client: AsyncClient, db_session: AsyncSession, alice: dict[str, str]
) -> None:
    monitor = await create(client, alice, is_public=True)
    await add_checks(
        db_session,
        monitor["id"],
        [
            (timedelta(days=20), CheckStatus.DOWN),
            (timedelta(days=3), CheckStatus.DOWN),
            (timedelta(hours=2), CheckStatus.DEGRADED),
            (timedelta(minutes=1), CheckStatus.UP),
        ],
    )

    body = (await client.get(f"{STATUS_API}/alice-co")).json()["monitors"][0]

    assert body["current_status"] == "up"
    assert body["uptime_24h"]["total"] == 2
    assert body["uptime_24h"]["percent"] == 100.0  # DEGRADED теж доступність
    assert body["uptime_7d"]["total"] == 3
    assert body["uptime_7d"]["down"] == 1
    assert body["uptime_30d"]["total"] == 4
    assert body["uptime_30d"]["percent"] == 50.0


async def test_monitor_without_checks_has_no_data(
    client: AsyncClient, alice: dict[str, str]
) -> None:
    await create(client, alice, is_public=True)

    body = (await client.get(f"{STATUS_API}/alice-co")).json()["monitors"][0]

    assert body["current_status"] is None
    assert body["last_checked_at"] is None
    assert body["uptime_24h"]["percent"] is None


async def test_unknown_slug_is_404(client: AsyncClient) -> None:
    response = await client.get(f"{STATUS_API}/nobody")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "status_page_not_found"


async def test_deactivated_owner_page_is_hidden(
    client: AsyncClient, db_session: AsyncSession, alice: dict[str, str]
) -> None:
    await db_session.execute(
        update(User).where(User.email == "alice@example.com").values(is_active=False)
    )

    response = await client.get(f"{STATUS_API}/alice-co")

    assert response.status_code == 404


async def test_is_public_flag_is_editable(client: AsyncClient, alice: dict[str, str]) -> None:
    monitor = await create(client, alice)
    assert monitor["is_public"] is False

    await client.patch(f"{MONITORS}/{monitor['id']}", json={"is_public": True}, headers=alice)

    assert len((await client.get(f"{STATUS_API}/alice-co")).json()["monitors"]) == 1


# HTML-сторінка


async def test_html_page_is_served_without_auth(client: AsyncClient) -> None:
    response = await client.get("/status/any-slug")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert '<script src="/static/status/status.js"' in response.text


@pytest.mark.parametrize(
    ("path", "content_type"),
    [("/static/status/status.js", "javascript"), ("/static/status/status.css", "text/css")],
)
async def test_static_assets_are_served(client: AsyncClient, path: str, content_type: str) -> None:
    response = await client.get(path)
    assert response.status_code == 200
    assert content_type in response.headers["content-type"]


async def test_script_never_uses_inner_html(client: AsyncClient) -> None:
    # Назви моніторів задає користувач, тож вставляти їх можна лише як текст
    script = (await client.get("/static/status/status.js")).text
    assert "innerHTML" not in script
