"""Authentication steps kept separate so a future OTP check can gate session creation."""

from datetime import datetime, timedelta, timezone
from secrets import token_urlsafe

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import LoginSession, User
from app.security import create_session_token, hash_session_token, verify_password


def authenticate_credentials(db: Session, user_id: str, password: str) -> User | None:
    """Verify the first login factor without issuing a session."""
    user = db.scalar(select(User).where(User.user_id == user_id.strip().lower()))
    stored_hash = user.password_hash if user is not None and user.is_active else None
    if not verify_password(password, stored_hash):
        return None
    return user


def create_login_session(db: Session, user: User) -> tuple[str, LoginSession]:
    """Issue a session after all required login factors have been verified."""
    settings = get_settings()
    now = datetime.now(timezone.utc)
    db.execute(delete(LoginSession).where(LoginSession.expires_at <= now))

    raw_token = create_session_token()
    login_session = LoginSession(
        user_id=user.id,
        token_hash=hash_session_token(raw_token),
        csrf_token=token_urlsafe(32),
        created_at=now,
        expires_at=now + timedelta(hours=settings.session_ttl_hours),
    )
    db.add(login_session)
    db.commit()
    return raw_token, login_session
