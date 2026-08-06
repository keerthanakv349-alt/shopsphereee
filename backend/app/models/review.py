"""
Review.

WHY ONE REVIEW PER (product_id, user_id):
Without this constraint, a customer could post the same review five
times to dominate a product's review section. The unique constraint
makes "edit your existing review" the only way to change your opinion,
which is both fairer to other shoppers and closer to how real review
systems behave.

WHY is_verified_purchase IS COMPUTED AT CREATE TIME, NOT LIVE:
It's set once, when the review is created, by checking whether an
OrderItem for this product+user exists at that moment — and then stored,
not re-derived on every read. If the customer later returns the item,
the "Verified Purchase" badge on their already-published review
shouldn't retroactively disappear; it records a historical fact ("this
person had bought it when they wrote this"), not a live status.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import GUID
from app.models.user import User  # noqa: F401  (resolves relationship string)


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (UniqueConstraint("product_id", "user_id", name="uq_review_product_user"),)

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    rating: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-5, validated in the schema
    title: Mapped[str | None] = mapped_column(String(150), nullable=True)
    comment: Mapped[str] = mapped_column(Text, nullable=False)
    is_verified_purchase: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    helpful_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_reported: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship()

    @property
    def reviewer_name(self) -> str:
        """Used by ReviewOut — a plain accessor, not a DB column, same
        pattern as Product.primary_image_url."""
        return self.user.full_name
