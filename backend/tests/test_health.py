from fastapi.testclient import TestClient

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
