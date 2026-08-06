"""
Notification.

WHY THIS TABLE EXISTS ALONGSIDE THE WEBSOCKET PUSH (core/ws_manager.py):
The WebSocket only delivers a notification to a user who happens to be
connected RIGHT NOW. Most of the time, they aren't — they placed an order
yesterday and aren't looking at the site when it ships today. Persisting
every notification here means "what happened while I was away" is
answerable by querying the DB (GET /api/v1/notifications), not lost the
moment nobody was listening on a socket. The WebSocket push is a
same-session convenience on top of this durable record, not a
replacement for it.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import GUID, pg_enum


class NotificationType(str, enum.Enum):
    ORDER_UPDATE = "order_update"
    PAYMENT_UPDATE = "payment_update"
    GENERAL = "general"


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    notification_type: Mapped[NotificationType] = mapped_column(
        pg_enum(NotificationType, name="notification_type"), default=NotificationType.GENERAL, nullable=False
    )
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    related_order_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("orders.id", ondelete="SET NULL"), nullable=True
    )
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
