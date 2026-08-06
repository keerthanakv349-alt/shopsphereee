import uuid
from decimal import Decimal

from pydantic import BaseModel, Field


class CartItemCreate(BaseModel):
    variant_id: uuid.UUID
    quantity: int = Field(ge=1, default=1)


class CartItemUpdate(BaseModel):
    quantity: int = Field(ge=1)


class CartItemOut(BaseModel):
    id: uuid.UUID
    variant_id: uuid.UUID
    product_id: uuid.UUID
    product_name: str
    product_slug: str
    sku: str
    size: str | None
    color: str | None
    unit_price: Decimal
    quantity: int
    line_total: Decimal
    stock_quantity: int
    image_url: str | None


class ApplyCouponRequest(BaseModel):
    code: str = Field(min_length=1, max_length=50)


class CartOut(BaseModel):
    id: uuid.UUID
    items: list[CartItemOut]
    subtotal: Decimal
    discount_amount: Decimal
    applied_coupon_code: str | None
    total: Decimal
