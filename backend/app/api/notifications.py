import asyncio
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.db import get_db, get_session_factory
from app.dependencies import AuthenticatedSession, get_current_auth, require_csrf
from app.models import Notification
from app.notifications import notification_hub
from app.schemas import NotificationPage, NotificationResponse, NotificationsMarkedRead


router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("/stream")
def stream_notifications(request: Request) -> StreamingResponse:
    # Authenticate with a short-lived session and close it before opening the SSE stream.
    with get_session_factory()() as db:
        user_id = get_current_auth(request, db).user.id

    async def events():
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=50)
        notification_hub.subscribe(user_id, loop, queue)
        try:
            yield "retry: 3000\n\n"
            while not await request.is_disconnected():
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=20)
                except TimeoutError:
                    yield ": keep-alive\n\n"
                else:
                    yield f"data: {payload}\n\n"
        finally:
            notification_hub.unsubscribe(user_id, loop, queue)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("", response_model=NotificationPage)
def list_notifications(
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthenticatedSession, Depends(get_current_auth)],
    limit: int = Query(default=30, ge=1, le=100),
) -> NotificationPage:
    unread_count = db.scalar(
        select(func.count(Notification.id)).where(
            Notification.user_id == auth.user.id,
            Notification.read_at.is_(None),
        )
    ) or 0
    items = db.scalars(
        select(Notification)
        .where(Notification.user_id == auth.user.id)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(limit)
    ).all()
    return NotificationPage(items=items, unread_count=unread_count)


@router.patch("/read-all", response_model=NotificationsMarkedRead, dependencies=[Depends(require_csrf)])
def mark_all_notifications_read(
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthenticatedSession, Depends(get_current_auth)],
) -> NotificationsMarkedRead:
    result = db.execute(
        update(Notification)
        .where(Notification.user_id == auth.user.id, Notification.read_at.is_(None))
        .values(read_at=datetime.now(timezone.utc))
    )
    db.commit()
    return NotificationsMarkedRead(updated_count=result.rowcount or 0)


@router.patch("/{notification_id}/read", response_model=NotificationResponse, dependencies=[Depends(require_csrf)])
def mark_notification_read(
    notification_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthenticatedSession, Depends(get_current_auth)],
) -> Notification:
    notification = db.scalar(
        select(Notification)
        .where(Notification.id == notification_id, Notification.user_id == auth.user.id)
        .with_for_update()
    )
    if notification is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    if notification.read_at is None:
        notification.read_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(notification)
    return notification
