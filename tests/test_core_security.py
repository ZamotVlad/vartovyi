import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.security import (
    TokenDecodeError,
    TokenType,
    create_token,
    decode_token,
    generate_api_key,
    hash_api_key,
    hash_password,
    verify_password,
)

SECRET = "x" * 32
ALG = "HS256"


def make(token_type: TokenType = TokenType.ACCESS, **kwargs: object) -> str:
    token, _ = create_token(
        uuid.uuid4(),
        token_type,
        ttl=timedelta(minutes=5),
        secret=SECRET,
        algorithm=ALG,
        **kwargs,  # type: ignore[arg-type]
    )
    return token


def test_password_hash_roundtrip() -> None:
    hashed = hash_password("correct horse")
    assert hashed != "correct horse"
    assert verify_password("correct horse", hashed)
    assert not verify_password("wrong horse", hashed)


def test_token_roundtrip_keeps_claims() -> None:
    user_id = uuid.uuid4()
    token, issued = create_token(
        user_id, TokenType.ACCESS, ttl=timedelta(minutes=5), secret=SECRET, algorithm=ALG
    )

    claims = decode_token(token, TokenType.ACCESS, secret=SECRET, algorithm=ALG)

    assert claims.subject == user_id
    assert claims.jti == issued.jti
    assert claims.token_type is TokenType.ACCESS


def test_each_token_gets_unique_jti() -> None:
    first = decode_token(make(), TokenType.ACCESS, secret=SECRET, algorithm=ALG)
    second = decode_token(make(), TokenType.ACCESS, secret=SECRET, algorithm=ALG)
    assert first.jti != second.jti


def test_refresh_token_is_not_accepted_as_access() -> None:
    with pytest.raises(TokenDecodeError):
        decode_token(make(TokenType.REFRESH), TokenType.ACCESS, secret=SECRET, algorithm=ALG)


def test_expired_token_is_rejected() -> None:
    token = make(now=datetime.now(UTC) - timedelta(hours=1))
    with pytest.raises(TokenDecodeError):
        decode_token(token, TokenType.ACCESS, secret=SECRET, algorithm=ALG)


def test_token_signed_with_other_secret_is_rejected() -> None:
    with pytest.raises(TokenDecodeError):
        decode_token(make(), TokenType.ACCESS, secret="y" * 32, algorithm=ALG)


def test_unsigned_token_is_rejected() -> None:
    payload = {"sub": str(uuid.uuid4()), "jti": "a", "type": "access", "exp": 9_999_999_999}
    token = jwt.encode(payload, key=None, algorithm="none")
    with pytest.raises(TokenDecodeError):
        decode_token(token, TokenType.ACCESS, secret=SECRET, algorithm=ALG)


def test_api_key_hash_is_deterministic_and_hides_key() -> None:
    raw = generate_api_key()
    assert raw.startswith("vtv_")
    assert hash_api_key(raw) == hash_api_key(raw)
    assert raw not in hash_api_key(raw)
    assert generate_api_key() != raw
