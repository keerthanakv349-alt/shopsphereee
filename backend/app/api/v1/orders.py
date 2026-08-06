"""
Checkout and order endpoints.

--- THE CHECKOUT TRANSACTION, STEP BY STEP ---
This is the single most important transaction in the whole system: it's
where money and inventory both change, and it has to be correct even when
multiple customers try to buy the last unit of something at the same
moment.

1. Load the customer's cart (must be non-empty) and the chosen address
   (must belong to them — see addresses.py's IDOR note, same principle).

2. For EVERY cart line, re-fetch the ProductVariant with `with_for_update()`
   — a row-level lock. Why this matters: without it, two customers who
   both have the last unit of a size in their cart could each read
   "stock_quantity = 1", both pass the "is there enough stock" check, and
   both successfully decrement it — one of them just oversold a product
   that doesn't exist. `with_for_update()` makes the second transaction
   WAIT until the first one commits (or rolls back), so it re-reads the
   now-current stock_quantity and correctly fails instead of overselling.
   This is THE classic race condition in e-commerce checkout, and locking
   is the standard fix (the alternative — optimistic concurrency with a
   retry loop — trades this simplicity for better throughput at higher
   scale; not needed yet here).

3. Re-validate price, discount, GST, and the coupon (if any) from
   scratch — never trust anything computed in an earlier request (cart
   view, apply-coupon). See app/core/coupons.py docstring for why.

4. Decrement each variant's stock_quantity, build snapshotted OrderItem
   rows (see app/models/order.py for why snapshotting matters), create
   the Order row, increment the coupon's times_used if one was applied,
   and clear the cart — ALL in one db.commit(). If anything raises before
   that commit, SQLAlchemy rolls back everything: no half-decremented
   stock, no order with missing items, no coupon usage counted without an
   order to match it.

5. Only after a successful commit do we return the created order.
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session, selectinload

from app.api.v1.deps import get_current_user
from app.core.coupons import calculate_discount, get_valid_coupon_or_raise
from app.core.rate_limit import CHECKOUT_RATE_LIMIT, limiter
from app.db.session import get_db
from app.models.address import Address
from app.models.cart import Cart, CartItem
from app.models.catalog import ProductVariant
from app.models.order import Order, OrderItem, OrderStatus
from app.models.user import User
from app.schemas.order import CheckoutRequest, OrderOut

router = APIRouter(prefix="/api/v1/orders", tags=["orders"])


def _generate_order_number() -> str:
    return f"ORD-{datetime.now(timezone.utc):%Y%m%d}-{uuid.uuid4().hex[:8].upper()}"


def _load_order_or_404(db: Session, order_id: uuid.UUID) -> Order:
    order = (
        db.query(Order).filter(Order.id == order_id).options(selectinload(Order.items)).first()
    )
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    return order


@router.post("", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
@limiter.limit(CHECKOUT_RATE_LIMIT)
def checkout(
    request: Request, payload: CheckoutRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    cart = db.query(Cart).filter(Cart.user_id == current_user.id).first()
    if cart is None or not cart.items:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Your cart is empty")

    address = (
        db.query(Address)
        .filter(Address.id == payload.address_id, Address.user_id == current_user.id)
        .first()
    )
    if address is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Address not found")

    order_items: list[OrderItem] = []
    subtotal = Decimal("0")
    gst_amount = Decimal("0")

    for cart_item in cart.items:
        # Row lock — see step 2 in the module docstring.
        variant = (
            db.query(ProductVariant)
            .filter(ProductVariant.id == cart_item.variant_id)
            .with_for_update()
            .first()
        )
        if variant is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "A product in your cart no longer exists")

        product = variant.product
        if variant.stock_quantity < cart_item.quantity:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Insufficient stock for {product.name} ({variant.sku}): "
                f"only {variant.stock_quantity} left",
            )

        base_unit_price = variant.price_override or product.base_price
        unit_price = base_unit_price - (base_unit_price * product.discount_percentage / Decimal("100"))
        line_total = unit_price * cart_item.quantity
        line_gst = line_total * product.gst_percentage / Decimal("100")

        subtotal += line_total
        gst_amount += line_gst

        variant.stock_quantity -= cart_item.quantity  # the actual inventory decrement

        order_items.append(
            OrderItem(
                product_id=product.id,
                variant_id=variant.id,
                product_name=product.name,
                sku=variant.sku,
                size=variant.size,
                color=variant.color,
                unit_price=unit_price,
                quantity=cart_item.quantity,
                line_total=line_total,
            )
        )

    discount_amount = Decimal("0")
    coupon = None
    if cart.applied_coupon_code:
        coupon = get_valid_coupon_or_raise(db, cart.applied_coupon_code, subtotal)
        discount_amount = calculate_discount(coupon, subtotal)

    total_amount = subtotal - discount_amount + gst_amount + payload.shipping_charge

    order = Order(
        order_number=_generate_order_number(),
        user_id=current_user.id,
        status=OrderStatus.PENDING,
        subtotal=subtotal,
        discount_amount=discount_amount,
        gst_amount=gst_amount,
        shipping_charge=payload.shipping_charge,
        total_amount=total_amount,
        coupon_code=cart.applied_coupon_code,
        shipping_full_name=address.full_name,
        shipping_phone_number=address.phone_number,
        shipping_line1=address.line1,
        shipping_line2=address.line2,
        shipping_city=address.city,
        shipping_state=address.state,
        shipping_postal_code=address.postal_code,
        shipping_country=address.country,
    )
    order.items = order_items
    db.add(order)

    if coupon is not None:
        coupon.times_used += 1

    for cart_item in list(cart.items):
        db.delete(cart_item)
    cart.applied_coupon_code = None

    db.commit()
    return _load_order_or_404(db, order.id)


@router.get("", response_model=list[OrderOut])
def list_my_orders(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return (
        db.query(Order)
        .filter(Order.user_id == current_user.id)
        .options(selectinload(Order.items))
        .order_by(Order.created_at.desc())
        .all()
    )


@router.get("/{order_id}", response_model=OrderOut)
def get_my_order(
    order_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    order = (
        db.query(Order)
        .filter(Order.id == order_id, Order.user_id == current_user.id)
        .options(selectinload(Order.items))
        .first()
    )
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    return order
