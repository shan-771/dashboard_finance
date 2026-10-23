from functools import lru_cache

from sqlalchemy import Engine, create_engine

from app.core.config import get_settings


class DatabaseNotConfiguredError(RuntimeError):
    """Raised when no database URL has been provided through configuration."""


@lru_cache
def get_engine() -> Engine:
    database_url = get_settings().database_url
    if database_url is None:
        raise DatabaseNotConfiguredError("DATABASE_URL is not configured")

    return create_engine(database_url.get_secret_value(), pool_pre_ping=True)
