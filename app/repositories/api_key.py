import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.db.models import ApiKey
from app.repositories.base import SqlRepository


class ApiKeyRepository(SqlRepository):
    async def add(self, api_key: ApiKey) -> ApiKey:
        self.session.add(api_key)
        await self.session.flush()
        return api_key

    async def get_for_user(self, key_id: uuid.UUID, user_id: uuid.UUID) -> ApiKey | None:
        stmt = select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == user_id)
        return await self.session.scalar(stmt)

    async def get_by_hash(self, key_hash: str) -> ApiKey | None:
        # Власник потрібен одразу, lazy load в async недоступний
        stmt = select(ApiKey).options(joinedload(ApiKey.user)).where(ApiKey.key_hash == key_hash)
        return await self.session.scalar(stmt)

    async def list_for_user(self, user_id: uuid.UUID) -> Sequence[ApiKey]:
        stmt = select(ApiKey).where(ApiKey.user_id == user_id).order_by(ApiKey.created_at.desc())
        result = await self.session.scalars(stmt)
        return result.all()
