from typing import Any

import pytest
from httpx import AsyncClient

from tests.helpers import auth_headers

MONITORS = "/api/v1/monitors"


def payload(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"name": "Сайт", "url": "https://example.com/health"}
    body.update(overrides)
    return body


async def create(client: AsyncClient, headers: dict[str, str], **overrides: Any) -> dict[str, Any]:
    response = await client.post(MONITORS, json=payload(**overrides), headers=headers)
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


@pytest.fixture
async def alice(client: AsyncClient) -> dict[str, str]:
    return await auth_headers(client, "alice@example.com")


@pytest.fixture
async def bob(client: AsyncClient) -> dict[str, str]:
    return await auth_headers(client, "bob@example.com")


# створення і читання


async def test_create_and_get(client: AsyncClient, alice: dict[str, str]) -> None:
    created = await create(client, alice, keyword="OK")

    response = await client.get(f"{MONITORS}/{created['id']}", headers=alice)

    assert response.status_code == 200
    body = response.json()
    assert body["url"] == "https://example.com/health"
    assert body["keyword"] == "OK"
    assert body["interval_seconds"] == 60
    assert "owner_id" not in body


async def test_create_validates_timing(client: AsyncClient, alice: dict[str, str]) -> None:
    response = await client.post(
        MONITORS, json=payload(interval_seconds=30, timeout_ms=45_000), headers=alice
    )
    assert response.status_code == 422


async def test_get_unknown_monitor(client: AsyncClient, alice: dict[str, str]) -> None:
    missing = "00000000-0000-0000-0000-000000000000"
    response = await client.get(f"{MONITORS}/{missing}", headers=alice)
    assert response.status_code == 404


# список


async def test_list_paginates(client: AsyncClient, alice: dict[str, str]) -> None:
    for i in range(5):
        await create(client, alice, name=f"m{i}")

    response = await client.get(MONITORS, params={"limit": 2, "offset": 2}, headers=alice)

    body = response.json()
    assert body["total"] == 5
    assert body["limit"] == 2
    assert body["offset"] == 2
    assert len(body["items"]) == 2


async def test_list_filters_and_sorts(client: AsyncClient, alice: dict[str, str]) -> None:
    await create(client, alice, name="b-api", url="https://api.example.com")
    await create(client, alice, name="a-api", url="https://api2.example.com")
    await create(client, alice, name="c-paused", is_active=False)

    active = await client.get(MONITORS, params={"is_active": True, "sort": "name"}, headers=alice)
    search = await client.get(MONITORS, params={"search": "paused"}, headers=alice)

    assert [m["name"] for m in active.json()["items"]] == ["a-api", "b-api"]
    assert search.json()["total"] == 1


@pytest.mark.parametrize(
    "params",
    [{"limit": 0}, {"limit": 101}, {"offset": -1}, {"sort": "owner_id"}, {"unknown": "x"}],
)
async def test_list_rejects_bad_params(
    client: AsyncClient, alice: dict[str, str], params: dict[str, Any]
) -> None:
    response = await client.get(MONITORS, params=params, headers=alice)
    assert response.status_code == 422


# часткове оновлення


async def test_patch_changes_only_sent_fields(client: AsyncClient, alice: dict[str, str]) -> None:
    created = await create(client, alice, keyword="OK")

    response = await client.patch(
        f"{MONITORS}/{created['id']}", json={"name": "Нова назва"}, headers=alice
    )

    body = response.json()
    assert response.status_code == 200
    assert body["name"] == "Нова назва"
    assert body["keyword"] == "OK"
    assert body["url"] == created["url"]


async def test_patch_null_clears_optional_field(client: AsyncClient, alice: dict[str, str]) -> None:
    created = await create(client, alice, keyword="OK")

    response = await client.patch(
        f"{MONITORS}/{created['id']}", json={"keyword": None}, headers=alice
    )

    assert response.json()["keyword"] is None


async def test_patch_rejects_null_for_required_field(
    client: AsyncClient, alice: dict[str, str]
) -> None:
    created = await create(client, alice)
    url = f"{MONITORS}/{created['id']}"
    response = await client.patch(url, json={"name": None}, headers=alice)
    assert response.status_code == 422


async def test_patch_checks_invariants_against_stored_state(
    client: AsyncClient, alice: dict[str, str]
) -> None:
    created = await create(client, alice, interval_seconds=60, timeout_ms=45_000)

    # Сам по собі interval_seconds=30 валідний, але конфліктує зі збереженим timeout_ms
    response = await client.patch(
        f"{MONITORS}/{created['id']}", json={"interval_seconds": 30}, headers=alice
    )

    assert response.status_code == 422
    unchanged = await client.get(f"{MONITORS}/{created['id']}", headers=alice)
    assert unchanged.json()["interval_seconds"] == 60


# видалення


async def test_delete(client: AsyncClient, alice: dict[str, str]) -> None:
    created = await create(client, alice)

    response = await client.delete(f"{MONITORS}/{created['id']}", headers=alice)

    assert response.status_code == 204
    assert (await client.get(f"{MONITORS}/{created['id']}", headers=alice)).status_code == 404


# хто НЕ має доступу


async def test_foreign_monitor_is_invisible(
    client: AsyncClient, alice: dict[str, str], bob: dict[str, str]
) -> None:
    created = await create(client, alice)
    url = f"{MONITORS}/{created['id']}"

    assert (await client.get(url, headers=bob)).status_code == 404
    assert (await client.patch(url, json={"name": "hacked"}, headers=bob)).status_code == 404
    assert (await client.delete(url, headers=bob)).status_code == 404
    listed = await client.get(MONITORS, headers=bob)
    assert listed.json()["total"] == 0

    still_there = await client.get(url, headers=alice)
    assert still_there.json()["name"] == created["name"]


async def test_foreign_and_missing_monitor_are_indistinguishable(
    client: AsyncClient, alice: dict[str, str], bob: dict[str, str]
) -> None:
    created = await create(client, alice)
    missing = "00000000-0000-0000-0000-000000000000"

    foreign = await client.get(f"{MONITORS}/{created['id']}", headers=bob)
    absent = await client.get(f"{MONITORS}/{missing}", headers=bob)

    assert foreign.status_code == absent.status_code == 404
    assert foreign.json() == absent.json()


async def test_monitor_endpoints_require_auth(client: AsyncClient, alice: dict[str, str]) -> None:
    created = await create(client, alice)
    url = f"{MONITORS}/{created['id']}"

    assert (await client.post(MONITORS, json=payload())).status_code == 401
    assert (await client.get(MONITORS)).status_code == 401
    assert (await client.get(url)).status_code == 401
    assert (await client.patch(url, json={"name": "x"})).status_code == 401
    assert (await client.delete(url)).status_code == 401


async def test_patch_url_is_normalized_and_saved(
    client: AsyncClient, alice: dict[str, str]
) -> None:
    created = await create(client, alice)
    url = f"{MONITORS}/{created['id']}"

    response = await client.patch(url, json={"url": "https://new.example.com/ping"}, headers=alice)

    assert response.json()["url"] == "https://new.example.com/ping"
    bad = await client.patch(url, json={"url": "not a url"}, headers=alice)
    assert bad.status_code == 422
