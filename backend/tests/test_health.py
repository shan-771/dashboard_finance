from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from app.core.config import get_settings
from app.db import DatabaseNotConfiguredError
from app.main import app


client = TestClient(app)


def test_health_reports_application_is_running() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_database_health_reports_missing_configuration(monkeypatch) -> None:
    def missing_database_configuration():
        raise DatabaseNotConfiguredError("DATABASE_URL is not configured")

    monkeypatch.setattr("app.api.health.get_engine", missing_database_configuration)
    response = client.get("/health/database")

    assert response.status_code == 503
    assert response.json() == {"detail": "Database is not configured"}


def test_database_health_reports_connection_and_business_timezone(monkeypatch) -> None:
    engine = create_engine("sqlite://")
    monkeypatch.setattr("app.api.health.get_engine", lambda: engine)
    try:
        response = client.get("/health/database")
    finally:
        engine.dispose()

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database": "ok",
        "business_timezone": get_settings().business_timezone,
    }


def test_auth_api_reports_missing_database_configuration(monkeypatch) -> None:
    def missing_database_configuration():
        raise DatabaseNotConfiguredError("DATABASE_URL is not configured")

    monkeypatch.setattr("app.db.get_session_factory", missing_database_configuration)
    response = client.get("/auth/me")

    assert response.status_code == 503
    assert response.json() == {"detail": "Database is not configured"}
