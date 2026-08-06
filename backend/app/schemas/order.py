import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.coupon import DiscountType
from app.models.order import OrderStatus


class CheckoutRequest(BaseModel):
    address_id: uuid.UUID
    # Shipping is a flat rate for Phase 3 — real carrier-rate shopping
    # (weight/distance-based) is a Phase 4+ concern once a delivery
    # partner integration exists to quote it.
    shipping_charge: Decimal = Field(default=Decimal("50.00"), ge=0)


class OrderItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    product_id: uuid.UUID | None
    product_name: str
    sku: str
    size: str | None
    color: str | None
    unit_price: Decimal
    quantity: int
    line_total: Decimal


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    order_number: str
    status: OrderStatus
    subtotal: Decimal
    discount_amount: Decimal
    gst_amount: Decimal
    shipping_charge: Decimal
    total_amount: Decimal
    coupon_code: str | None
    shipping_full_name: str
    shipping_phone_number: str
    shipping_line1: str
    shipping_line2: str | None
    shipping_city: str
    shipping_state: str
    shipping_postal_code: str
    shipping_country: str
    created_at: datetime
    items: list[OrderItemOut]


class OrderStatusUpdate(BaseModel):
    status: OrderStatus


class CouponCreate(BaseModel):
    code: str = Field(min_length=3, max_length=50)
    discount_type: DiscountType
    discount_value: Decimal = Field(gt=0)
    max_discount_amount: Decimal | None = Field(default=None, gt=0)
    min_order_value: Decimal = Field(default=Decimal("0"), ge=0)
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    usage_limit: int | None = Field(default=None, ge=1)


class CouponOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    code: str
    discount_type: DiscountType
    discount_value: Decimal
    max_discount_amount: Decimal | None
    min_order_value: Decimal
    valid_from: datetime | None
    valid_until: datetime | None
    usage_limit: int | None
    times_used: int
    is_active: bool
