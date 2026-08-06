"""
DeliveryPartner & TrackingEvent.

WHY TRACKING IS AN APPEND-ONLY EVENT LOG, NOT A SINGLE "current status"
FIELD ON ORDER:
Order already has a `status` column (Phase 3) for the fulfillment
lifecycle (pending/packed/shipped/...). TrackingEvent is a DIFFERENT,
finer-grained concept: the shipment's physical journey — "left the
Mumbai hub," "arrived at the Pune facility," "out for delivery, 3 stops
away." A single "current location" field could only ever show the LATEST
point; a real tracking page (and the map on it) needs the whole trail.
Appending a new row per event, never updating old ones, is what makes
"show me this order's full journey" possible at all.

WHY DeliveryPartner IS A SEPARATE TABLE:
Real logistics involves assigning a specific courier/rider to a shipment
— their name and contact number are what the customer actually wants
when they ask "who has my package." Keeping it separate from User means
delivery partners aren't customers or admins; they're a third kind of
actor the system needs to reference, not authenticate (no login for them
in this phase — a real system might give delivery partners their own
mobile app and auth, which is a further phase of its own).
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import GUID, pg_enum


class TrackingStatus(str, enum.Enum):
    ORDER_PACKED = "order_packed"
    SHIPPED = "shipped"
    IN_TRANSIT = "in_transit"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"


class DeliveryPartner(Base):
    __tablename__ = "delivery_partners"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    phone_number: Mapped[str] = mapped_column(String(20), nullable=False)
    vehicle_number: Mapped[str | None] = mapped_column(String(30), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TrackingEvent(Base):
    __tablename__ = "tracking_events"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    delivery_partner_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("delivery_partners.id", ondelete="SET NULL"), nullable=True
    )

    status: Mapped[TrackingStatus] = mapped_column(pg_enum(TrackingStatus, name="tracking_status"), nullable=False)
    location_label: Mapped[str | None] = mapped_column(String(150), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    delivery_partner: Mapped["DeliveryPartner | None"] = relationship()
