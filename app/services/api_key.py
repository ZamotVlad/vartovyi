import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import API_KEY_VISIBLE_CHARS, generate_api_key, hash_api_key
from app.db.models import ApiKey, User
from app.domain.errors import ApiKeyNotFoundError
from app.repositories.api_key import ApiKeyRepository


class ApiKeyService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.api_keys = ApiKeyRepository(session)

    async def create(self, user: User, name: str) -> tuple[ApiKey, str]:
        """Повертає модель і сирий ключ. Сирий ключ більше ніде не зберігається."""
        raw_key = generate_api_key()
        api_key = ApiKey(
            user_id=user.id,
            name=name,
            prefix=raw_key[:API_KEY_VISIBLE_CHARS],
            key_hash=hash_api_key(raw_key),
        )
        await self.api_keys.add(api_key)
        await self.session.commit()
        return api_key, raw_key

    async def list_for_user(self, user: User) -> Sequence[ApiKey]:
        return await self.api_keys.list_for_user(user.id)

    async def revoke(self, user: User, key_id: uuid.UUID) -> None:
        # Чужий ключ і неіснуючий неможливо розрізнити ззовні
        api_key = await self.api_keys.get_for_user(key_id, user.id)
        if api_key is None:
            raise ApiKeyNotFoundError
        if api_key.revoked_at is None:
            api_key.revoked_at = datetime.now(UTC)
            await self.session.commit()
