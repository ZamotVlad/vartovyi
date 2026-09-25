from datetime import UTC, datetime

from redis.asyncio import Redis


class TokenBlacklist:
    """Відкликані jti в Redis. Запис живе рівно до природного закінчення токена."""

    KEY_PREFIX = "auth:revoked:"

    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    async def revoke(self, jti: str, expires_at: datetime) -> bool:
        """Атомарно відкликає токен. False, якщо його вже відкликали раніше.

        Саме атомарність (SET NX) не дає двом паралельним /refresh
        з одним токеном обидва отримати нову пару.
        """
        ttl = max(int((expires_at - datetime.now(UTC)).total_seconds()), 1)
        created = await self.redis.set(self.KEY_PREFIX + jti, "1", ex=ttl, nx=True)
        return bool(created)

    async def is_revoked(self, jti: str) -> bool:
        return bool(await self.redis.exists(self.KEY_PREFIX + jti))
