from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "MI FINS CRM API"
    app_env: Literal["development", "production"] = "development"
    database_url: SecretStr | None = None
    session_cookie_name: str = "mi_fins_session"
    session_ttl_hours: int = Field(default=12, ge=1, le=168)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("database_url", mode="before")
    @classmethod
    def validate_database_url(cls, value: object) -> object:
        if value is None or value == "":
            return None

        raw_url = value.get_secret_value() if isinstance(value, SecretStr) else value
        if not isinstance(raw_url, str) or not raw_url.startswith(
            ("postgresql://", "postgresql+psycopg://")
        ):
            raise ValueError("DATABASE_URL must use PostgreSQL with the psycopg driver")
        return value

    @property
    def session_cookie_secure(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
