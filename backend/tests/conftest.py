from collections.abc import Iterator
from typing import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import get_db
from app.main import app
from app.models import Base, User, UserRole
from app.security import hash_password


@pytest.fixture
def test_session_factory() -> Iterator[sessionmaker[Session]]:
    engine: Engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    try:
        yield factory
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def client(test_session_factory: sessionmaker[Session]) -> Iterator[TestClient]:
    def override_get_db() -> Iterator[Session]:
        db = test_session_factory()
        try:
            yield db
        finally:
            db.close()

    previous_sweeper_state = getattr(app.state, "enable_retention_sweeper", True)
    app.state.enable_retention_sweeper = False
    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        app.state.enable_retention_sweeper = previous_sweeper_state


@pytest.fixture
def make_user(
    test_session_factory: sessionmaker[Session],
) -> Callable[..., User]:
    def create_user(
        *,
        email: str = "manager@example.com",
        password: str = "correct horse battery staple",
        role: UserRole = UserRole.MANAGER,
        is_active: bool = True,
    ) -> User:
        db = test_session_factory()
        try:
            user = User(
                email=email,
                user_id=email.split("@")[0].lower(),
                display_name="Test User",
                password_hash=hash_password(password),
                role=role.value,
                is_active=is_active,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            return user
        finally:
            db.close()

    return create_user
