"""
Order & OrderItem.

THE MOST IMPORTANT DESIGN DECISION IN THIS FILE: SNAPSHOTTING.

An Order does NOT rely on live Product/ProductVariant/Address data for
historical accuracy — it copies (snapshots) the values that matter at the
moment of purchase directly onto OrderItem and Order:
  - OrderItem stores product_name, sku, size, color, and unit_price as
    plain columns, not just a product_id/variant_id FK.
  - Order stores the full shipping address as plain columns, not just an
    address_id FK.

WHY: imagine a customer orders a shoe at ₹8999. Two weeks later, the
admin changes the price to ₹7499, or renames the product, or deletes it
entirely, or the customer edits/deletes that address. If OrderItem only
stored foreign keys and looked up "current" product data to render an
order history page, that customer's past order would silently show the
WRONG price and possibly break entirely (FK pointing at a deleted row).
Real invoices and order confirmations must reflect what was TRUE AT
PURCHASE TIME, forever — so we copy the data in, once, at checkout.
product_id/variant_id/address fields are still kept as nullable
references for convenience (e.g. "show me this product's other reviews"),
but nothing about rendering the order depends on them still existing.

ORDER STATUS LIFECYCLE (per the brief):
pending → packed → shipped → out_for_delivery → delivered
                                                 → cancelled (from pending/packed only)
                                                 → returned → refunded
Modeled as a single enum column rather than a separate "order_status_
history" table for Phase 3 — a full audit trail of every status
transition (who changed it, when) is a natural Phase 5/6 addition
(Tracking History from the original schema list) once delivery-partner
integration exists to actually drive those transitions.
"""
import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import GUID, pg_enum


class OrderStatus(str, enum.Enum):
    PENDING = "pending"
    PACKED = "packed"
    SHIPPED = "shipped"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    RETURNED = "returned"
    REFUNDED = "refunded"


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    order_number: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    status: Mapped[OrderStatus] = mapped_column(
        pg_enum(OrderStatus, name="order_status"), default=OrderStatus.PENDING, nullable=False, index=True
    )

    subtotal: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
    gst_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
    shipping_charge: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    coupon_code: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # --- Shipping address SNAPSHOT (see module docstring) ---
    shipping_full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    shipping_phone_number: Mapped[str] = mapped_column(String(20), nullable=False)
    shipping_line1: Mapped[str] = mapped_column(String(255), nullable=False)
    shipping_line2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    shipping_city: Mapped[str] = mapped_column(String(100), nullable=False)
    shipping_state: Mapped[str] = mapped_column(String(100), nullable=False)
    shipping_postal_code: Mapped[str] = mapped_column(String(20), nullable=False)
    shipping_country: Mapped[str] = mapped_column(String(100), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Nullable references — convenience only, never load-bearing for display.
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )
    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("product_variants.id", ondelete="SET NULL"), nullable=True
    )

    # --- Product SNAPSHOT (see module docstring) ---
    product_name: Mapped[str] = mapped_column(String(200), nullable=False)
    sku: Mapped[str] = mapped_column(String(64), nullable=False)
    size: Mapped[str | None] = mapped_column(String(20), nullable=True)
    color: Mapped[str | None] = mapped_column(String(40), nullable=True)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    order: Mapped["Order"] = relationship(back_populates="items")
