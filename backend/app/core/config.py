from functools import lru_cache

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "MI FINS CRM API"
    database_url: SecretStr | None = None

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
