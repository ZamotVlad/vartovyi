from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    check_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    check_max_concurrency: int = Field(default=50, ge=1, le=500)


@lru_cache
def get_settings() -> Settings:
    return Settings()
