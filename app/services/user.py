from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.domain.errors import StatusSlugTakenError
from app.repositories.user import UserRepository
from app.schemas.auth import UserUpdate


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)

    async def update(self, user: User, data: UserUpdate) -> User:
        slug = data.status_slug
        if slug is not None and slug != user.status_slug:
            taken = await self.users.get_by_status_slug(slug)
            if taken is not None:
                raise StatusSlugTakenError
        user.status_slug = slug
        try:
            await self.session.commit()
        except IntegrityError as exc:
            # Хтось зайняв ту саму адресу між перевіркою і commit
            await self.session.rollback()
            raise StatusSlugTakenError from exc
        return user
