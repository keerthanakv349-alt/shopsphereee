"""
Cart endpoints. Every route operates on "the current user's cart" — there
is no cart_id in any URL, because a customer only ever has one cart (see
the unique constraint on Cart.user_id) and should never be able to
reference anyone else's.
"""
import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, selectinload

from app.api.v1.deps import get_current_user
from app.core.coupons import calculate_discount, get_valid_coupon_or_raise
from app.db.session import get_db
from app.models.cart import Cart, CartItem
from app.models.catalog import ProductStatus, ProductVariant
from app.models.user import User
from app.schemas.cart import ApplyCouponRequest, CartItemCreate, CartItemOut, CartItemUpdate, CartOut

router = APIRouter(prefix="/api/v1/cart", tags=["cart"])


def _get_or_create_cart(db: Session, user: User) -> Cart:
    cart = db.query(Cart).filter(Cart.user_id == user.id).first()
    if cart is None:
        cart = Cart(user_id=user.id)
        db.add(cart)
        db.commit()
        db.refresh(cart)
    return cart


def _serialize_cart(db: Session, cart: Cart) -> CartOut:
    cart = (
        db.query(Cart)
        .filter(Cart.id == cart.id)
        .options(
            selectinload(Cart.items).selectinload(CartItem.variant).selectinload(ProductVariant.product)
        )
        .first()
    )

    item_outs: list[CartItemOut] = []
    subtotal = Decimal("0")
    for item in cart.items:
        variant = item.variant
        product = variant.product
        unit_price = variant.price_override or product.base_price
        # Discount from the product carries through to the cart line —
        # what the customer pays, not the pre-discount list price.
        effective_price = unit_price - (unit_price * product.discount_percentage / Decimal("100"))
        line_total = effective_price * item.quantity
        subtotal += line_total

        item_outs.append(
            CartItemOut(
                id=item.id,
                variant_id=variant.id,
                product_id=product.id,
                product_name=product.name,
                product_slug=product.slug,
                sku=variant.sku,
                size=variant.size,
                color=variant.color,
                unit_price=effective_price,
                quantity=item.quantity,
                line_total=line_total,
                stock_quantity=variant.stock_quantity,
                image_url=product.primary_image_url,
            )
        )

    discount_amount = Decimal("0")
    if cart.applied_coupon_code:
        try:
            coupon = get_valid_coupon_or_raise(db, cart.applied_coupon_code, subtotal)
            discount_amount = calculate_discount(coupon, subtotal)
        except HTTPException:
            # The coupon that was valid when applied is no longer valid
            # (expired, cart total dropped below minimum, etc) — silently
            # drop it from the cart rather than error out just from
            # VIEWING the cart. Checkout re-validates and gives a clear
            # error there if the customer tries to use it anyway.
            cart.applied_coupon_code = None
            db.commit()

    return CartOut(
        id=cart.id,
        items=item_outs,
        subtotal=subtotal,
        discount_amount=discount_amount,
        applied_coupon_code=cart.applied_coupon_code,
        total=subtotal - discount_amount,
    )


@router.get("", response_model=CartOut)
def get_cart(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    cart = _get_or_create_cart(db, current_user)
    return _serialize_cart(db, cart)


@router.post("/items", response_model=CartOut, status_code=status.HTTP_201_CREATED)
def add_item(
    payload: CartItemCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    variant = db.get(ProductVariant, payload.variant_id)
    if variant is None or variant.product.status != ProductStatus.ACTIVE:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product variant not found")

    cart = _get_or_create_cart(db, current_user)
    existing = (
        db.query(CartItem).filter(CartItem.cart_id == cart.id, CartItem.variant_id == variant.id).first()
    )

    already_in_cart = existing.quantity if existing else 0
    requested_total = already_in_cart + payload.quantity
    if requested_total > variant.stock_quantity:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Only {variant.stock_quantity} in stock (you already have {already_in_cart} in your cart)",
        )

    if existing:
        existing.quantity = requested_total
    else:
        db.add(CartItem(cart_id=cart.id, variant_id=variant.id, quantity=payload.quantity))

    db.commit()
    return _serialize_cart(db, cart)


@router.put("/items/{item_id}", response_model=CartOut)
def update_item(
    item_id: uuid.UUID,
    payload: CartItemUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cart = _get_or_create_cart(db, current_user)
    item = db.query(CartItem).filter(CartItem.id == item_id, CartItem.cart_id == cart.id).first()
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cart item not found")

    if payload.quantity > item.variant.stock_quantity:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Only {item.variant.stock_quantity} in stock")

    item.quantity = payload.quantity
    db.commit()
    return _serialize_cart(db, cart)


@router.delete("/items/{item_id}", response_model=CartOut)
def remove_item(
    item_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    cart = _get_or_create_cart(db, current_user)
    item = db.query(CartItem).filter(CartItem.id == item_id, CartItem.cart_id == cart.id).first()
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cart item not found")

    db.delete(item)
    db.commit()
    return _serialize_cart(db, cart)


@router.post("/apply-coupon", response_model=CartOut)
def apply_coupon(
    payload: ApplyCouponRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cart = _get_or_create_cart(db, current_user)
    current = _serialize_cart(db, cart)
    if not current.items:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Your cart is empty")

    # Validate before saving — raises a clear 400/404 if the code is bad,
    # rather than silently attaching an invalid coupon to the cart.
    get_valid_coupon_or_raise(db, payload.code, current.subtotal)

    cart.applied_coupon_code = payload.code.upper()
    db.commit()
    return _serialize_cart(db, cart)


@router.delete("/coupon", response_model=CartOut)
def remove_coupon(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    cart = _get_or_create_cart(db, current_user)
    cart.applied_coupon_code = None
    db.commit()
    return _serialize_cart(db, cart)
