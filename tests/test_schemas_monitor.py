import pytest
from pydantic import ValidationError

from app.schemas.monitor import MonitorCreate, MonitorUpdate


def valid_payload(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "name": "Мій сайт",
        "url": "https://example.com/health",
        "interval_seconds": 60,
        "timeout_ms": 10_000,
    }
    base.update(overrides)
    return base


def test_minimal_payload_uses_defaults() -> None:
    monitor = MonitorCreate.model_validate({"name": "Сайт", "url": "https://example.com"})
    assert monitor.interval_seconds == 60
    assert monitor.expected_status == 200
    assert monitor.is_active is True
    assert monitor.keyword is None


def test_rejects_non_http_scheme() -> None:
    with pytest.raises(ValidationError):
        MonitorCreate.model_validate({"name": "Сайт", "url": "ftp://example.com"})


def test_rejects_garbage_url() -> None:
    with pytest.raises(ValidationError):
        MonitorCreate.model_validate({"name": "Сайт", "url": "просто текст"})


def test_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError):
        MonitorCreate.model_validate(valid_payload(nmae="одруківка"))


def test_rejects_too_frequent_interval() -> None:
    with pytest.raises(ValidationError):
        MonitorCreate.model_validate(valid_payload(interval_seconds=5))


def test_rejects_timeout_longer_than_interval() -> None:
    with pytest.raises(ValidationError) as exc:
        MonitorCreate.model_validate(valid_payload(interval_seconds=30, timeout_ms=45_000))
    assert "накладатись" in str(exc.value)


def test_rejects_unreachable_degradation_threshold() -> None:
    with pytest.raises(ValidationError) as exc:
        MonitorCreate.model_validate(valid_payload(timeout_ms=2_000, max_response_ms=5_000))
    assert "недосяжний" in str(exc.value)


def test_accepts_threshold_below_timeout() -> None:
    monitor = MonitorCreate.model_validate(valid_payload(timeout_ms=5_000, max_response_ms=2_000))
    assert monitor.max_response_ms == 2_000


def test_empty_name_is_rejected() -> None:
    with pytest.raises(ValidationError):
        MonitorCreate.model_validate(valid_payload(name=""))


def test_update_distinguishes_omitted_from_explicit_null() -> None:
    omitted = MonitorUpdate(name="Нова назва")
    explicit = MonitorUpdate(keyword=None)

    assert "keyword" not in omitted.model_dump(exclude_unset=True)
    assert "keyword" in explicit.model_dump(exclude_unset=True)
    assert explicit.model_dump(exclude_unset=True)["keyword"] is None


def test_update_allows_empty_patch() -> None:
    assert MonitorUpdate().model_dump(exclude_unset=True) == {}
