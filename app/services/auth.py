from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.core.security import (
    DUMMY_PASSWORD_HASH,
    TokenClaims,
    TokenDecodeError,
    TokenType,
    create_token,
    decode_token,
    hash_api_key,
    hash_password,
    verify_password,
)
from app.db.models import User
from app.domain.errors import (
    EmailAlreadyRegisteredError,
    InactiveUserError,
    InvalidCredentialsError,
    InvalidTokenError,
)
from app.repositories.api_key import ApiKeyRepository
from app.repositories.token_blacklist import TokenBlacklist
from app.repositories.user import UserRepository
from app.schemas.auth import TokenPair, UserCreate


class AuthService:
    def __init__(
        self, session: AsyncSession, blacklist: TokenBlacklist, settings: Settings
    ) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.api_keys = ApiKeyRepository(session)
        self.blacklist = blacklist
        self.settings = settings

    async def register(self, data: UserCreate) -> User:
        email = data.email.lower()
        if await self.users.get_by_email(email) is not None:
            raise EmailAlreadyRegisteredError
        user = User(email=email, hashed_password=hash_password(data.password))
        try:
            await self.users.add(user)
            await self.session.commit()
        except IntegrityError as exc:
            # Паралельна реєстрація з тим самим email проскочила перевірку вище
            await self.session.rollback()
            raise EmailAlreadyRegisteredError from exc
        return user

    async def login(self, email: str, password: str) -> TokenPair:
        user = await self.users.get_by_email(email.lower())
        if user is None:
            verify_password(password, DUMMY_PASSWORD_HASH)
            raise InvalidCredentialsError
        if not verify_password(password, user.hashed_password):
            raise InvalidCredentialsError
        if not user.is_active:
            raise InactiveUserError
        return self._issue_pair(user)

    async def refresh(self, refresh_token: str) -> TokenPair:
        claims = self._decode(refresh_token, TokenType.REFRESH)
        # Ротація: старий refresh стає недійсним у момент видачі нового
        if not await self.blacklist.revoke(claims.jti, claims.expires_at):
            raise InvalidTokenError
        user = await self.users.get(claims.subject)
        if user is None:
            raise InvalidTokenError
        if not user.is_active:
            raise InactiveUserError
        return self._issue_pair(user)

    async def logout(self, access_token: str, refresh_token: str) -> None:
        access = await self._verified_claims(access_token, TokenType.ACCESS)
        refresh = self._decode(refresh_token, TokenType.REFRESH)
        # Не можна відкликати чужий refresh, маючи лише свій access
        if refresh.subject != access.subject:
            raise InvalidTokenError
        await self.blacklist.revoke(access.jti, access.expires_at)
        await self.blacklist.revoke(refresh.jti, refresh.expires_at)

    async def user_from_access_token(self, token: str) -> User:
        claims = await self._verified_claims(token, TokenType.ACCESS)
        user = await self.users.get(claims.subject)
        if user is None:
            raise InvalidTokenError
        return user

    async def user_from_api_key(self, raw_key: str) -> User:
        api_key = await self.api_keys.get_by_hash(hash_api_key(raw_key))
        if api_key is None or api_key.is_revoked:
            raise InvalidTokenError
        api_key.last_used_at = datetime.now(UTC)
        await self.session.commit()
        return api_key.user

    def _issue_pair(self, user: User) -> TokenPair:
        secret = self.settings.jwt_secret_key.get_secret_value()
        algorithm = self.settings.jwt_algorithm
        access_ttl = self.settings.access_token_ttl_seconds
        access, _ = create_token(
            user.id,
            TokenType.ACCESS,
            ttl=timedelta(seconds=access_ttl),
            secret=secret,
            algorithm=algorithm,
        )
        refresh, _ = create_token(
            user.id,
            TokenType.REFRESH,
            ttl=timedelta(seconds=self.settings.refresh_token_ttl_seconds),
            secret=secret,
            algorithm=algorithm,
        )
        return TokenPair(access_token=access, refresh_token=refresh, expires_in=access_ttl)

    def _decode(self, token: str, expected: TokenType) -> TokenClaims:
        try:
            return decode_token(
                token,
                expected,
                secret=self.settings.jwt_secret_key.get_secret_value(),
                algorithm=self.settings.jwt_algorithm,
            )
        except TokenDecodeError as exc:
            raise InvalidTokenError from exc

    async def _verified_claims(self, token: str, expected: TokenType) -> TokenClaims:
        claims = self._decode(token, expected)
        if await self.blacklist.is_revoked(claims.jti):
            raise InvalidTokenError
        return claims
