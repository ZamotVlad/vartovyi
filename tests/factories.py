import uuid
from datetime import UTC, datetime
from typing import Any

from app.db.models import Monitor, User


def make_user(email: str = "owner@example.com") -> User:
    # Хеш не справжній: репозиторним тестам пароль не потрібен
    return User(email=email, hashed_password="not-a-real-hash")


def make_monitor(owner_id: uuid.UUID, **overrides: Any) -> Monitor:
    values: dict[str, Any] = {
        "owner_id": owner_id,
        "name": "Сайт",
        "url": "https://example.com",
        "interval_seconds": 60,
        "timeout_ms": 10_000,
        "expected_status": 200,
    }
    values.update(overrides)
    return Monitor(**values)


def at(minute: int, hour: int = 12) -> datetime:
    return datetime(2026, 1, 1, hour, minute, tzinfo=UTC)
