import respx
from httpx import AsyncClient

from tests.helpers import auth_headers
from tests.test_api_monitors import MONITORS, create


@respx.mock
async def test_run_check_now(client: AsyncClient) -> None:
    respx.get("https://example.com/health").respond(200, text="all good")
    alice = await auth_headers(client, "alice@example.com")
    monitor = await create(client, alice, keyword="good")

    response = await client.post(f"{MONITORS}/{monitor['id']}/checks", headers=alice)

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "up"
    assert body["status_code"] == 200
    assert body["monitor_id"] == monitor["id"]

    refreshed = await client.get(f"{MONITORS}/{monitor['id']}", headers=alice)
    assert refreshed.json()["last_checked_at"] is not None


@respx.mock
async def test_run_check_reports_failure_reason(client: AsyncClient) -> None:
    respx.get("https://example.com/health").respond(200, text="maintenance")
    alice = await auth_headers(client, "alice@example.com")
    monitor = await create(client, alice, keyword="good")

    body = (await client.post(f"{MONITORS}/{monitor['id']}/checks", headers=alice)).json()

    assert body["status"] == "down"
    assert "good" in body["reason"]


@respx.mock
async def test_list_checks_newest_first(client: AsyncClient) -> None:
    respx.get("https://example.com/health").respond(200)
    alice = await auth_headers(client, "alice@example.com")
    monitor = await create(client, alice)
    url = f"{MONITORS}/{monitor['id']}/checks"
    for _ in range(3):
        await client.post(url, headers=alice)

    body = (await client.get(url, params={"limit": 2}, headers=alice)).json()

    assert body["total"] == 3
    assert len(body["items"]) == 2
    assert body["items"][0]["created_at"] >= body["items"][1]["created_at"]


@respx.mock
async def test_foreign_monitor_checks_are_invisible(client: AsyncClient) -> None:
    route = respx.get("https://example.com/health").respond(200)
    alice = await auth_headers(client, "alice@example.com")
    bob = await auth_headers(client, "bob@example.com")
    monitor = await create(client, alice)
    url = f"{MONITORS}/{monitor['id']}/checks"

    assert (await client.post(url, headers=bob)).status_code == 404
    assert (await client.get(url, headers=bob)).status_code == 404
    # Чужий користувач не може навіть змусити нас зробити запит до цілі
    assert not route.called


async def test_check_endpoints_require_auth(client: AsyncClient) -> None:
    alice = await auth_headers(client, "alice@example.com")
    monitor = await create(client, alice)
    url = f"{MONITORS}/{monitor['id']}/checks"

    assert (await client.post(url)).status_code == 401
    assert (await client.get(url)).status_code == 401


@respx.mock
async def test_monitor_list_embeds_latest_check(client: AsyncClient) -> None:
    respx.get("https://example.com/health").respond(503)
    alice = await auth_headers(client, "alice@example.com")
    checked = await create(client, alice, name="a")
    await create(client, alice, name="b")
    await client.post(f"{MONITORS}/{checked['id']}/checks", headers=alice)

    items = (await client.get(MONITORS, params={"sort": "name"}, headers=alice)).json()["items"]

    assert items[0]["latest_check"]["status"] == "down"
    assert items[0]["latest_check"]["status_code"] == 503
    assert items[1]["latest_check"] is None
