import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

import jwt
from passlib.context import CryptContext

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

API_KEY_PREFIX = "vtv_"
API_KEY_VISIBLE_CHARS = 12


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return _pwd_context.verify(password, hashed)


# Хеш для порівняння, коли користувача не знайдено: вирівнює час відповіді,
# щоб за ним не можна було визначити, чи зареєстрований email
DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(16))


class TokenType(StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"


class TokenDecodeError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class TokenClaims:
    subject: uuid.UUID
    jti: str
    token_type: TokenType
    expires_at: datetime


def create_token(
    subject: uuid.UUID,
    token_type: TokenType,
    *,
    ttl: timedelta,
    secret: str,
    algorithm: str,
    now: datetime | None = None,
) -> tuple[str, TokenClaims]:
    issued_at = now or datetime.now(UTC)
    claims = TokenClaims(
        subject=subject,
        jti=uuid.uuid4().hex,
        token_type=token_type,
        expires_at=issued_at + ttl,
    )
    payload = {
        "sub": str(subject),
        "jti": claims.jti,
        "type": token_type.value,
        "iat": issued_at,
        "exp": claims.expires_at,
    }
    return jwt.encode(payload, secret, algorithm=algorithm), claims


def decode_token(
    token: str, expected_type: TokenType, *, secret: str, algorithm: str
) -> TokenClaims:
    try:
        # algorithms явно: інакше токен міг би сам обрати алгоритм (атака alg=none)
        payload = jwt.decode(
            token,
            secret,
            algorithms=[algorithm],
            options={"require": ["sub", "jti", "type", "exp"]},
        )
        claims = TokenClaims(
            subject=uuid.UUID(payload["sub"]),
            jti=str(payload["jti"]),
            token_type=TokenType(payload["type"]),
            expires_at=datetime.fromtimestamp(payload["exp"], tz=UTC),
        )
    except (jwt.PyJWTError, ValueError, TypeError) as exc:
        raise TokenDecodeError(str(exc)) from exc

    # Refresh-токен не повинен відкривати API, і навпаки
    if claims.token_type is not expected_type:
        raise TokenDecodeError(f"expected {expected_type} token")
    return claims


def generate_api_key() -> str:
    return API_KEY_PREFIX + secrets.token_urlsafe(32)


def hash_api_key(raw_key: str) -> str:
    # Ключ має 256 біт випадковості, тож перебір неможливий і bcrypt не потрібен.
    # Швидкий детермінований хеш дозволяє шукати ключ по індексу
    return hashlib.sha256(raw_key.encode()).hexdigest()
