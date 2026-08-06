"""
Coupon.

DESIGN NOTES:
- discount_type (percentage vs flat) + discount_value covers both
  "10% off" and "₹200 off" with one table instead of two.
- max_discount_amount caps a percentage coupon ("20% off, up to ₹500") —
  without this, a 20%-off coupon on a ₹50,000 order gives an unbounded
  ₹10,000 discount, which is virtually never what a business intends for
  a percentage promo.
- usage_limit + times_used enables "first 100 customers only" style
  coupons. times_used is incremented inside the SAME transaction as order
  creation (see orders.py) — never as a separate step, or a burst of
  concurrent checkouts could all read "times_used=99, limit=100" and all
  succeed, overselling the coupon by however many requests raced.
- valid_from/valid_until are both nullable: a coupon can be open-ended on
  either side (no start restriction, or no expiry) — modeling "always
  valid" as a magic date range would be more error-prone than allowing
  NULL to mean "no restriction" here.
"""
import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import GUID, pg_enum


class DiscountType(str, enum.Enum):
    PERCENTAGE = "percentage"
    FLAT = "flat"


class Coupon(Base):
    __tablename__ = "coupons"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)

    discount_type: Mapped[DiscountType] = mapped_column(pg_enum(DiscountType, name="discount_type"), nullable=False)
    discount_value: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    max_discount_amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    min_order_value: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))

    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    usage_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    times_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
