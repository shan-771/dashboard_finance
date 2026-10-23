from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import require_csrf, require_manager
from app.models import LoginSession, User, UserRole
from app.schemas import CreateStaffRequest, StaffStatusUpdate, UserResponse
from app.security import hash_password


router = APIRouter(prefix="/users", tags=["staff accounts"])


@router.get("", response_model=list[UserResponse], dependencies=[Depends(require_manager)])
def list_users(db: Annotated[Session, Depends(get_db)]) -> list[User]:
    return list(db.scalars(select(User).order_by(User.created_at, User.email)).all())


@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_manager), Depends(require_csrf)],
)
def create_staff_user(
    payload: CreateStaffRequest,
    db: Annotated[Session, Depends(get_db)],
) -> User:
    user = User(
        user_id=payload.user_id,
        email=str(payload.email).strip().lower(),
        display_name=payload.display_name or payload.user_id,
        password_hash=hash_password(payload.password.get_secret_value()),
        role=UserRole.STAFF.value,
        is_active=True,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User ID or email is already in use",
        ) from exc
    db.refresh(user)
    return user


@router.patch(
    "/{user_id}/status",
    response_model=UserResponse,
    dependencies=[Depends(require_manager), Depends(require_csrf)],
)
def update_staff_status(
    user_id: UUID,
    payload: StaffStatusUpdate,
    db: Annotated[Session, Depends(get_db)],
) -> User:
    user = db.get(User, user_id)
    if user is None or user.role != UserRole.STAFF.value:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Staff account not found")

    user.is_active = payload.is_active
    if not user.is_active:
        db.execute(delete(LoginSession).where(LoginSession.user_id == user.id))
    db.commit()
    db.refresh(user)
    return user
