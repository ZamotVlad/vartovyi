import uuid

from sqlalchemy import select

from app.db.models import User
from app.repositories.base import SqlRepository


class UserRepository(SqlRepository):
    async def add(self, user: User) -> User:
        self.session.add(user)
        await self.session.flush()
        return user

    async def get(self, user_id: uuid.UUID) -> User | None:
        return await self.session.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        return await self.session.scalar(select(User).where(User.email == email))

    async def get_by_status_slug(self, slug: str) -> User | None:
        return await self.session.scalar(select(User).where(User.status_slug == slug))
