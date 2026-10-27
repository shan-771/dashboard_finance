from fastapi import APIRouter, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.db import DatabaseNotConfiguredError, get_engine


router = APIRouter(tags=["health"])


@router.get("/health")
def read_health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/database")
def read_database_health() -> dict[str, str]:
    try:
        engine = get_engine()
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except DatabaseNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail="Database is not configured") from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Database is unavailable") from exc

    return {
        "status": "ok",
        "database": "ok",
        "business_timezone": get_settings().business_timezone,
    }
