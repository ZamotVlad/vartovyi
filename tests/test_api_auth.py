from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from tests.helpers import AUTH, PASSWORD, auth_headers, bearer, login, register


async def deactivate(session: AsyncSession, email: str) -> None:
    await session.execute(update(User).where(User.email == email).values(is_active=False))
    await session.flush()


# register


async def test_register_returns_user_without_password(client: AsyncClient) -> None:
    body = await register(client, "New.User@Example.com")

    assert body["email"] == "new.user@example.com"
    assert body["is_active"] is True
    assert "password" not in body
    assert "hashed_password" not in body


async def test_register_duplicate_email_case_insensitive(client: AsyncClient) -> None:
    await register(client, "user@example.com")

    response = await client.post(
        f"{AUTH}/register", json={"email": "USER@example.com", "password": PASSWORD}
    )

    assert response.status_code == 409


async def test_register_rejects_short_password(client: AsyncClient) -> None:
    response = await client.post(
        f"{AUTH}/register", json={"email": "a@example.com", "password": "short"}
    )
    assert response.status_code == 422


async def test_register_rejects_password_longer_than_bcrypt_limit(client: AsyncClient) -> None:
    response = await client.post(
        f"{AUTH}/register", json={"email": "a@example.com", "password": "ї" * 40}
    )
    assert response.status_code == 422


# login


async def test_login_returns_token_pair(client: AsyncClient) -> None:
    await register(client)
    tokens = await login(client, "USER@example.com")

    assert tokens["token_type"] == "bearer"
    assert tokens["access_token"] != tokens["refresh_token"]
    assert tokens["expires_in"] > 0


async def test_login_wrong_password(client: AsyncClient) -> None:
    await register(client)
    response = await client.post(
        f"{AUTH}/login", data={"username": "user@example.com", "password": "wrong-password"}
    )
    assert response.status_code == 401


async def test_login_unknown_email_looks_like_wrong_password(client: AsyncClient) -> None:
    response = await client.post(
        f"{AUTH}/login", data={"username": "ghost@example.com", "password": PASSWORD}
    )
    assert response.status_code == 401


async def test_login_inactive_user(client: AsyncClient, db_session: AsyncSession) -> None:
    await register(client)
    await deactivate(db_session, "user@example.com")

    response = await client.post(
        f"{AUTH}/login", data={"username": "user@example.com", "password": PASSWORD}
    )

    assert response.status_code == 403


# me і ланцюжок залежностей


async def test_me_with_access_token(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    response = await client.get(f"{AUTH}/me", headers=headers)
    assert response.status_code == 200
    assert response.json()["email"] == "user@example.com"


async def test_me_without_credentials(client: AsyncClient) -> None:
    response = await client.get(f"{AUTH}/me")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


async def test_me_with_garbage_token(client: AsyncClient) -> None:
    response = await client.get(f"{AUTH}/me", headers=bearer("not-a-jwt"))
    assert response.status_code == 401


async def test_me_rejects_refresh_token(client: AsyncClient) -> None:
    await register(client)
    tokens = await login(client)
    response = await client.get(f"{AUTH}/me", headers=bearer(tokens["refresh_token"]))
    assert response.status_code == 401


async def test_me_inactive_user_is_forbidden(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await auth_headers(client)
    await deactivate(db_session, "user@example.com")

    response = await client.get(f"{AUTH}/me", headers=headers)

    assert response.status_code == 403


# refresh


async def test_refresh_rotates_tokens(client: AsyncClient) -> None:
    await register(client)
    tokens = await login(client)

    response = await client.post(f"{AUTH}/refresh", json={"refresh_token": tokens["refresh_token"]})

    assert response.status_code == 200
    new = response.json()
    assert new["refresh_token"] != tokens["refresh_token"]
    me = await client.get(f"{AUTH}/me", headers=bearer(new["access_token"]))
    assert me.status_code == 200


async def test_refresh_token_cannot_be_reused(client: AsyncClient) -> None:
    await register(client)
    tokens = await login(client)
    payload = {"refresh_token": tokens["refresh_token"]}

    first = await client.post(f"{AUTH}/refresh", json=payload)
    second = await client.post(f"{AUTH}/refresh", json=payload)

    assert first.status_code == 200
    assert second.status_code == 401


async def test_refresh_rejects_access_token(client: AsyncClient) -> None:
    await register(client)
    tokens = await login(client)
    response = await client.post(f"{AUTH}/refresh", json={"refresh_token": tokens["access_token"]})
    assert response.status_code == 401


# logout


async def test_logout_revokes_both_tokens(client: AsyncClient) -> None:
    await register(client)
    tokens = await login(client)
    headers = bearer(tokens["access_token"])

    response = await client.post(
        f"{AUTH}/logout", json={"refresh_token": tokens["refresh_token"]}, headers=headers
    )

    assert response.status_code == 204
    assert (await client.get(f"{AUTH}/me", headers=headers)).status_code == 401
    refresh = await client.post(f"{AUTH}/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refresh.status_code == 401


async def test_logout_requires_access_token(client: AsyncClient) -> None:
    await register(client)
    tokens = await login(client)
    response = await client.post(f"{AUTH}/logout", json={"refresh_token": tokens["refresh_token"]})
    assert response.status_code == 401


async def test_logout_cannot_revoke_someone_elses_refresh(client: AsyncClient) -> None:
    await register(client, "alice@example.com")
    await register(client, "bob@example.com")
    alice = await login(client, "alice@example.com")
    bob = await login(client, "bob@example.com")

    response = await client.post(
        f"{AUTH}/logout",
        json={"refresh_token": bob["refresh_token"]},
        headers=bearer(alice["access_token"]),
    )

    assert response.status_code == 401
    still_valid = await client.post(f"{AUTH}/refresh", json={"refresh_token": bob["refresh_token"]})
    assert still_valid.status_code == 200


async def test_refresh_for_deactivated_user(client: AsyncClient, db_session: AsyncSession) -> None:
    await register(client)
    tokens = await login(client)
    await deactivate(db_session, "user@example.com")

    response = await client.post(f"{AUTH}/refresh", json={"refresh_token": tokens["refresh_token"]})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "inactive_user"


async def test_api_key_of_deactivated_user_is_forbidden(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    headers = await auth_headers(client)
    created = await client.post(f"{AUTH}/api-keys", json={"name": "ci"}, headers=headers)
    await deactivate(db_session, "user@example.com")

    response = await client.get(f"{AUTH}/me", headers={"X-API-Key": created.json()["key"]})

    assert response.status_code == 403
