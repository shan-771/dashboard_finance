import asyncio
import json
import threading
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Notification, User, UserRole


class NotificationHub:
    """Push committed notifications to connected sessions in this API process."""

    def __init__(self) -> None:
        self._subscribers: dict[UUID, set[tuple[asyncio.AbstractEventLoop, asyncio.Queue[str]]]] = {}
        self._lock = threading.Lock()

    def subscribe(
        self, user_id: UUID, loop: asyncio.AbstractEventLoop, queue: asyncio.Queue[str]
    ) -> None:
        with self._lock:
            self._subscribers.setdefault(user_id, set()).add((loop, queue))

    def unsubscribe(
        self, user_id: UUID, loop: asyncio.AbstractEventLoop, queue: asyncio.Queue[str]
    ) -> None:
        with self._lock:
            subscribers = self._subscribers.get(user_id)
            if subscribers is None:
                return
            subscribers.discard((loop, queue))
            if not subscribers:
                self._subscribers.pop(user_id, None)

    def publish(self, user_id: UUID, payload: dict[str, str | None]) -> None:
        data = json.dumps(payload, separators=(",", ":"))
        with self._lock:
            subscribers = tuple(self._subscribers.get(user_id, ()))
        for loop, queue in subscribers:
            def enqueue(target: asyncio.Queue[str] = queue, event_data: str = data) -> None:
                if target.full():
                    try:
                        target.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                target.put_nowait(event_data)

            if not loop.is_closed():
                loop.call_soon_threadsafe(enqueue)


notification_hub = NotificationHub()


def notify_users(
    db: Session,
    user_ids: list[UUID],
    *,
    notification_type: str,
    title: str,
    message: str,
    enquiry_id: UUID,
) -> list[Notification]:
    notifications = []
    for user_id in set(user_ids):
        notification = Notification(
            user_id=user_id,
            notification_type=notification_type,
            title=title,
            message=message,
            enquiry_id=enquiry_id,
        )
        db.add(notification)
        notifications.append(notification)
    return notifications


def notify_active_role(
    db: Session,
    role: UserRole,
    *,
    notification_type: str,
    title: str,
    message: str,
    enquiry_id: UUID,
) -> list[Notification]:
    user_ids = list(db.scalars(select(User.id).where(User.role == role.value, User.is_active.is_(True))).all())
    return notify_users(
        db,
        user_ids,
        notification_type=notification_type,
        title=title,
        message=message,
        enquiry_id=enquiry_id,
    )


def publish_notifications(notifications: list[Notification]) -> None:
    for notification in notifications:
        notification_hub.publish(notification.user_id, {
            "id": str(notification.id),
            "notification_type": notification.notification_type,
            "title": notification.title,
            "message": notification.message,
            "enquiry_id": str(notification.enquiry_id),
            "created_at": notification.created_at.isoformat(),
            "read_at": notification.read_at.isoformat() if notification.read_at else None,
        })
