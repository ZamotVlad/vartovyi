import pytest
from pydantic import ValidationError

from app.config import LOCAL_JWT_SECRET, Settings, get_settings


def test_local_environment_allows_dev_secret() -> None:
    assert Settings().jwt_secret_key.get_secret_value() == LOCAL_JWT_SECRET


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_dev_secret_is_rejected_outside_local(environment: str) -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET_KEY"):
        Settings(environment=environment)  # type: ignore[arg-type]


def test_real_secret_is_accepted_in_production() -> None:
    settings = Settings(environment="production", jwt_secret_key="p" * 64)  # type: ignore[arg-type]
    assert settings.environment == "production"


def test_short_secret_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(jwt_secret_key="short")  # type: ignore[arg-type]


def test_settings_are_cached() -> None:
    assert get_settings() is get_settings()
