import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.delivery import TrackingStatus


class DeliveryPartnerCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    phone_number: str = Field(min_length=6, max_length=20)
    vehicle_number: str | None = Field(default=None, max_length=30)


class DeliveryPartnerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    phone_number: str
    vehicle_number: str | None
    is_active: bool


class TrackingEventCreate(BaseModel):
    status: TrackingStatus
    location_label: str | None = Field(default=None, max_length=150)
    latitude: float | None = None
    longitude: float | None = None
    note: str | None = Field(default=None, max_length=1000)
    delivery_partner_id: uuid.UUID | None = None


class TrackingEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    status: TrackingStatus
    location_label: str | None
    latitude: float | None
    longitude: float | None
    note: str | None
    created_at: datetime
    delivery_partner: DeliveryPartnerOut | None
