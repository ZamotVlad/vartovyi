from httpx import AsyncClient

from tests.helpers import AUTH, auth_headers


async def create_key(client: AsyncClient, headers: dict[str, str], name: str = "ci") -> str:
    response = await client.post(f"{AUTH}/api-keys", json={"name": name}, headers=headers)
    assert response.status_code == 201, response.text
    key: str = response.json()["key"]
    return key


async def test_api_key_authenticates_requests(client: AsyncClient) -> None:
    key = await create_key(client, await auth_headers(client))

    response = await client.get(f"{AUTH}/me", headers={"X-API-Key": key})

    assert response.status_code == 200
    assert response.json()["email"] == "user@example.com"


async def test_raw_key_is_shown_only_once(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    key = await create_key(client, headers)

    listed = (await client.get(f"{AUTH}/api-keys", headers=headers)).json()

    assert len(listed) == 1
    assert "key" not in listed[0]
    assert key.startswith(listed[0]["prefix"])
    assert listed[0]["last_used_at"] is None


async def test_usage_updates_last_used_at(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    key = await create_key(client, headers)

    await client.get(f"{AUTH}/me", headers={"X-API-Key": key})

    listed = (await client.get(f"{AUTH}/api-keys", headers=headers)).json()
    assert listed[0]["last_used_at"] is not None


async def test_unknown_api_key_is_rejected(client: AsyncClient) -> None:
    response = await client.get(f"{AUTH}/me", headers={"X-API-Key": "vtv_forged"})
    assert response.status_code == 401


async def test_revoked_api_key_is_rejected(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    key = await create_key(client, headers)
    key_id = (await client.get(f"{AUTH}/api-keys", headers=headers)).json()[0]["id"]

    revoked = await client.delete(f"{AUTH}/api-keys/{key_id}", headers=headers)

    assert revoked.status_code == 204
    response = await client.get(f"{AUTH}/me", headers={"X-API-Key": key})
    assert response.status_code == 401


async def test_cannot_revoke_someone_elses_key(client: AsyncClient) -> None:
    alice = await auth_headers(client, "alice@example.com")
    bob = await auth_headers(client, "bob@example.com")
    await create_key(client, alice)
    alice_key_id = (await client.get(f"{AUTH}/api-keys", headers=alice)).json()[0]["id"]

    response = await client.delete(f"{AUTH}/api-keys/{alice_key_id}", headers=bob)

    assert response.status_code == 404


async def test_list_shows_only_own_keys(client: AsyncClient) -> None:
    alice = await auth_headers(client, "alice@example.com")
    bob = await auth_headers(client, "bob@example.com")
    await create_key(client, alice)

    listed = (await client.get(f"{AUTH}/api-keys", headers=bob)).json()

    assert listed == []


async def test_api_key_endpoints_require_auth(client: AsyncClient) -> None:
    assert (await client.post(f"{AUTH}/api-keys", json={"name": "x"})).status_code == 401
    assert (await client.get(f"{AUTH}/api-keys")).status_code == 401
    missing = "00000000-0000-0000-0000-000000000000"
    assert (await client.delete(f"{AUTH}/api-keys/{missing}")).status_code == 401
