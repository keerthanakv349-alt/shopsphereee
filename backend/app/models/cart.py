"""
Cart & CartItem.

WHY THE CART LIVES ON THE SERVER (not just frontend localStorage):
A localStorage-only cart disappears if the customer switches devices, and
can't be safely price/stock-checked at checkout without a round trip
anyway. Persisting it server-side, keyed to the logged-in user, means
"add to cart on your phone, check out on your laptop" just works, and
lets us validate current price/stock every time the cart is read — a
customer never sees a cart total that's silently gone stale.

WHY (user_id, variant_id) IS UNIQUE:
Adding "the same size+color shoe" to the cart twice should increase the
quantity on the existing line, not create a second row for the same
variant. That's enforced by a unique constraint here rather than trusted
to always-correct application code — the DB rejects a duplicate insert
even if a bug (or a retried request) tries to create one.

WHY applied_coupon_code IS STORED ON THE CART:
The coupon is validated (min order value, expiry, usage limit) once at
"apply" time so the UI can show the discount immediately, but it is
ALWAYS re-validated again at actual checkout (see orders.py) — never
trust a value computed earlier in a separate request. Storing just the
code (not the computed discount amount) means there's only one source of
truth for "what does this coupon do," calculated fresh each time.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import GUID
from app.models.catalog import ProductVariant  # noqa: F401  (resolves relationship string)


class Cart(Base):
    __tablename__ = "carts"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    applied_coupon_code: Mapped[str | None] = mapped_column(String(50), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    items: Mapped[list["CartItem"]] = relationship(back_populates="cart", cascade="all, delete-orphan")


class CartItem(Base):
    __tablename__ = "cart_items"
    __table_args__ = (UniqueConstraint("cart_id", "variant_id", name="uq_cart_variant"),)

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    cart_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("carts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    variant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("product_variants.id", ondelete="CASCADE"), nullable=False
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    cart: Mapped["Cart"] = relationship(back_populates="items")
    variant: Mapped["ProductVariant"] = relationship()
