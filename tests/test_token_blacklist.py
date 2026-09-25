from datetime import UTC, datetime, timedelta

from fakeredis.aioredis import FakeRedis

from app.repositories.token_blacklist import TokenBlacklist


async def test_revoke_is_atomic_first_wins(redis: FakeRedis) -> None:
    blacklist = TokenBlacklist(redis)
    expires = datetime.now(UTC) + timedelta(minutes=5)

    assert await blacklist.revoke("jti-1", expires) is True
    assert await blacklist.revoke("jti-1", expires) is False
    assert await blacklist.is_revoked("jti-1")
    assert not await blacklist.is_revoked("jti-2")


async def test_revoked_entry_expires_with_token(redis: FakeRedis) -> None:
    blacklist = TokenBlacklist(redis)
    await blacklist.revoke("jti-1", datetime.now(UTC) + timedelta(seconds=90))

    ttl = await redis.ttl(TokenBlacklist.KEY_PREFIX + "jti-1")

    assert 0 < ttl <= 90
