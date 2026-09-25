from datetime import UTC, datetime
from typing import Any

from app.db.models import Monitor


def make_monitor(**overrides: Any) -> Monitor:
    values: dict[str, Any] = {
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
