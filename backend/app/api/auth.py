from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.auth_service import authenticate_credentials, create_login_session
from app.db import get_db
from app.dependencies import AuthenticatedSession, get_current_auth, require_csrf
from app.models import LoginSession
from app.schemas import AuthResponse, LoginRequest, UserResponse


router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/login", response_model=AuthResponse)
def login(
    payload: LoginRequest,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> AuthResponse:
    response.headers["Cache-Control"] = "no-store"
    user = authenticate_credentials(db, payload.user_id, payload.password.get_secret_value())
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user ID or password",
        )

    settings = get_settings()
    raw_token, login_session = create_login_session(db, user)

    response.set_cookie(
        key=settings.session_cookie_name,
        value=raw_token,
        max_age=settings.session_ttl_hours * 60 * 60,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )
    return AuthResponse(user=UserResponse.model_validate(user), csrf_token=login_session.csrf_token)


@router.get("/me", response_model=AuthResponse)
def read_current_user(
    auth: Annotated[AuthenticatedSession, Depends(get_current_auth)],
    response: Response,
) -> AuthResponse:
    response.headers["Cache-Control"] = "no-store"
    return AuthResponse(
        user=UserResponse.model_validate(auth.user),
        csrf_token=auth.session.csrf_token,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def logout(
    auth: Annotated[AuthenticatedSession, Depends(get_current_auth)],
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[None, Depends(require_csrf)],
) -> Response:
    settings = get_settings()
    db.delete(auth.session)
    db.commit()

    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="lax",
    )
    return response
