from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Лише для локальної розробки: поза local валідатор вимагає справжній секрет
LOCAL_JWT_SECRET = "local-dev-secret-do-not-use-in-production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
    )

    app_name: str = "Vartovyi"
    environment: Literal["local", "staging", "production"] = "local"
    debug: bool = False

    api_v1_prefix: str = "/api/v1"

    database_url: str = "postgresql+asyncpg://vartovyi:vartovyi@localhost:5432/vartovyi"
    database_echo: bool = False

    redis_url: str = "redis://localhost:6379/0"

    jwt_secret_key: SecretStr = Field(default=SecretStr(LOCAL_JWT_SECRET), min_length=32)
    jwt_algorithm: Literal["HS256"] = "HS256"
    access_token_ttl_seconds: int = Field(default=15 * 60, ge=60)
    refresh_token_ttl_seconds: int = Field(default=7 * 24 * 3600, ge=3600)

    check_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    check_max_concurrency: int = Field(default=50, ge=1, le=500)

    @model_validator(mode="after")
    def require_real_secret_outside_local(self) -> Self:
        if self.environment != "local" and (
            self.jwt_secret_key.get_secret_value() == LOCAL_JWT_SECRET
        ):
            raise ValueError("JWT_SECRET_KEY обов'язковий поза середовищем local")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
