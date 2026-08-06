"""
Coupon validation and discount calculation.

WHY THIS IS ONE SHARED FUNCTION, CALLED TWICE:
The cart's "apply coupon" endpoint calls this to show the customer their
discount immediately. Checkout calls it AGAIN, independently, right before
creating the order. This is deliberate, not redundant: minutes can pass
between "apply coupon" and "place order" — the coupon might expire, hit
its usage limit from another customer's concurrent checkout, or the cart
contents might change such that min_order_value is no longer met. Trusting
a discount amount computed earlier and just copying it onto the order
would let a customer lock in a coupon that's no longer valid. Recomputing
from scratch, from the SAME function, guarantees the two call sites can
never silently disagree with each other.
"""
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.coupon import Coupon, DiscountType


def get_valid_coupon_or_raise(db: Session, code: str, order_subtotal: Decimal) -> Coupon:
    coupon = db.query(Coupon).filter(Coupon.code == code.upper()).first()
    if coupon is None or not coupon.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invalid coupon code")

    now = datetime.now(timezone.utc)
    if coupon.valid_from and now < coupon.valid_from:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This coupon is not active yet")
    if coupon.valid_until and now > coupon.valid_until:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This coupon has expired")
    if coupon.usage_limit is not None and coupon.times_used >= coupon.usage_limit:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This coupon has reached its usage limit")
    if order_subtotal < coupon.min_order_value:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"This coupon requires a minimum order value of {coupon.min_order_value}",
        )
    return coupon


def calculate_discount(coupon: Coupon, order_subtotal: Decimal) -> Decimal:
    if coupon.discount_type == DiscountType.FLAT:
        discount = coupon.discount_value
    else:
        discount = order_subtotal * (coupon.discount_value / Decimal("100"))
        if coupon.max_discount_amount is not None:
            discount = min(discount, coupon.max_discount_amount)

    # Never let a coupon discount more than the order itself is worth.
    return min(discount, order_subtotal)
