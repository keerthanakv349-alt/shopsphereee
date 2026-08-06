import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.notification import NotificationType


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    notification_type: NotificationType
    title: str
    message: str
    related_order_id: uuid.UUID | None
    is_read: bool
    created_at: datetime
