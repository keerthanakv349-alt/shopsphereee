"""
notify_user: the single call site every part of the app uses to tell a
user something happened.

WHY THIS IS ONE FUNCTION, CALLED FROM ORDER STATUS UPDATES, PAYMENT
VERIFICATION, AND TRACKING EVENTS:
Every "something happened to your order/payment" moment needs the same
two things to happen together: persist a Notification row (so it's there
next time they check, even if they weren't online) and push it live over
WebSocket (so it's there INSTANTLY if they are). Having every call site
independently do both would risk them drifting — someone adds a new
notification trigger and forgets the WebSocket push, or vice versa.
Centralizing it here means both always happen together.

WHY THIS RUNS INLINE IN THE REQUEST, NOT VIA A BACKGROUND QUEUE:
A production system would push this through Celery/a task queue so a
slow or dead WebSocket send can't add latency to the admin's "update
order status" request. Inline is simpler to reason about and fully
correct for this scope; the docstring on ConnectionManager already flags
the related "single process only" limitation as Phase 7 territory.
"""
import uuid

from sqlalchemy.orm import Session

from app.core.ws_manager import connection_manager
from app.models.notification import Notification, NotificationType


async def notify_user(
    db: Session,
    user_id: uuid.UUID,
    title: str,
    message: str,
    notification_type: NotificationType = NotificationType.GENERAL,
    related_order_id: uuid.UUID | None = None,
) -> Notification:
    notification = Notification(
        user_id=user_id,
        notification_type=notification_type,
        title=title,
        message=message,
        related_order_id=related_order_id,
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)

    await connection_manager.send_to_user(
        user_id,
        {
            "id": str(notification.id),
            "type": notification.notification_type.value,
            "title": notification.title,
            "message": notification.message,
            "related_order_id": str(related_order_id) if related_order_id else None,
            "created_at": notification.created_at.isoformat(),
        },
    )
    return notification
