from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.models import LoginSession, User, UserRole


PASSWORD = "correct horse battery staple"


def sign_in(client: TestClient, user_id: str, password: str = PASSWORD):
    return client.post("/auth/login", json={"user_id": user_id, "password": password})


def test_manager_can_sign_in_and_read_own_profile(client: TestClient, make_user) -> None:
    user = make_user()

    response = sign_in(client, user.user_id)

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["email"] == user.email
    assert body["user"]["user_id"] == user.user_id
    assert body["user"]["role"] == "manager"
    assert body["csrf_token"]
    assert "password_hash" not in body["user"]
    assert "httponly" in response.headers["set-cookie"].lower()
    assert "samesite=lax" in response.headers["set-cookie"].lower()

    profile = client.get("/auth/me")
    assert profile.status_code == 200
    assert profile.json()["user"]["id"] == str(user.id)


def test_login_user_id_is_case_insensitive(client: TestClient, make_user) -> None:
    user = make_user(email="Sam.Manager@example.com")

    response = sign_in(client, user.user_id.upper())

    assert response.status_code == 200
    assert response.json()["user"]["user_id"] == user.user_id


def test_invalid_or_inactive_credentials_are_rejected(client: TestClient, make_user) -> None:
    make_user()
    make_user(email="inactive@example.com", is_active=False)

    wrong_password = sign_in(client, "manager", "wrong password")
    inactive_user = sign_in(client, "inactive")
    unknown_user = sign_in(client, "unknown")

    assert wrong_password.status_code == 401
    assert inactive_user.status_code == 401
    assert unknown_user.status_code == 401
    assert wrong_password.json() == {"detail": "Invalid user ID or password"}


def test_staff_cannot_access_manager_account_list(client: TestClient, make_user) -> None:
    staff = make_user(email="staff@example.com", role=UserRole.STAFF)
    assert sign_in(client, staff.user_id).status_code == 200

    response = client.get("/users")

    assert response.status_code == 403


def test_user_routes_require_authentication(client: TestClient) -> None:
    response = client.get("/users")

    assert response.status_code == 401


def test_manager_can_create_staff_but_cannot_choose_their_role(
    client: TestClient,
    make_user,
    test_session_factory: sessionmaker[Session],
) -> None:
    manager = make_user()
    login = sign_in(client, manager.user_id)
    csrf_token = login.json()["csrf_token"]

    response = client.post(
        "/users",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "user_id": "new.staff",
            "email": "new.staff@example.com",
            "display_name": "New Staff",
            "password": "a sufficiently long password",
            "role": "manager",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["role"] == "staff"
    assert body["user_id"] == "new.staff"
    assert body["is_active"] is True
    with test_session_factory() as db:
        stored_user = db.query(User).filter_by(email="new.staff@example.com").one()
        assert stored_user.password_hash != "a sufficiently long password"


def test_manager_account_changes_require_csrf(client: TestClient, make_user) -> None:
    manager = make_user()
    sign_in(client, manager.user_id)

    response = client.post(
        "/users",
        json={
            "user_id": "new.staff",
            "email": "new.staff@example.com",
            "display_name": "New Staff",
            "password": "a sufficiently long password",
        },
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Invalid CSRF token"}


def test_deactivating_staff_revokes_existing_sessions(
    client: TestClient,
    make_user,
    test_session_factory: sessionmaker[Session],
) -> None:
    manager = make_user()
    staff = make_user(email="staff@example.com", role=UserRole.STAFF)
    sign_in(client, manager.user_id)
    csrf_token = client.get("/auth/me").json()["csrf_token"]

    with TestClient(client.app) as staff_client:
        assert sign_in(staff_client, staff.user_id).status_code == 200
        with test_session_factory() as db:
            staff_row = db.get(User, staff.id)
            assert staff_row is not None
            staff_id = str(staff_row.id)

        response = client.patch(
            f"/users/{staff_id}/status",
            headers={"X-CSRF-Token": csrf_token},
            json={"is_active": False},
        )
        assert response.status_code == 200
        assert response.json()["is_active"] is False

        assert staff_client.get("/auth/me").status_code == 401
        with test_session_factory() as db:
            assert db.query(LoginSession).filter_by(user_id=staff.id).count() == 0


def test_logout_revokes_session_and_clears_cookie(client: TestClient, make_user) -> None:
    user = make_user()
    login = sign_in(client, user.user_id)
    csrf_token = login.json()["csrf_token"]

    response = client.post("/auth/logout", headers={"X-CSRF-Token": csrf_token})

    assert response.status_code == 204
    assert client.get("/auth/me").status_code == 401
