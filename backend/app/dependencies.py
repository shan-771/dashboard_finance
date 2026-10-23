from dataclasses import dataclass
from datetime import datetime, timezone
from secrets import compare_digest
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import get_db
from app.models import LoginSession, User, UserRole
from app.security import hash_session_token


@dataclass(frozen=True)
class AuthenticatedSession:
    user: User
    session: LoginSession


def get_current_auth(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> AuthenticatedSession:
    settings = get_settings()
    raw_token = request.cookies.get(settings.session_cookie_name)
    if not raw_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    login_session = db.scalar(
        select(LoginSession).where(LoginSession.token_hash == hash_session_token(raw_token))
    )
    if login_session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    expires_at = login_session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= datetime.now(timezone.utc):
        db.delete(login_session)
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")

    user = db.get(User, login_session.user_id)
    if user is None or not user.is_active:
        db.delete(login_session)
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    return AuthenticatedSession(user=user, session=login_session)


def require_manager(
    auth: Annotated[AuthenticatedSession, Depends(get_current_auth)],
) -> User:
    if auth.user.role != UserRole.MANAGER.value:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Manager access required")
    return auth.user


def require_csrf(
    auth: Annotated[AuthenticatedSession, Depends(get_current_auth)],
    csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> None:
    if not csrf_token or not compare_digest(auth.session.csrf_token, csrf_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token")
