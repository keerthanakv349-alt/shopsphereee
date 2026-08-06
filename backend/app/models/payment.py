"""
Payment.

WHY PAYMENT IS ITS OWN TABLE, SEPARATE FROM ORDER:
An order can have MULTIPLE payment attempts — a card gets declined, the
customer tries again with a different method, or a payment is later
refunded. Bolting "payment status" fields directly onto Order would only
ever capture the most recent attempt and lose that history. A separate
Payment row per attempt (one order_id can have many Payment rows) means
"why did this order take three tries to pay for" is answerable from the
data, and Payment History (an explicit item in the original brief) is
just "list Payment rows," not something reconstructed from mutated Order
fields.

WHY amount IS STORED HERE TOO (not just read from Order.total_amount):
Order.total_amount could theoretically be edited later (a manual admin
adjustment, a partial refund changing what's "owed") — Payment.amount
snapshots exactly what THIS attempt was for, same snapshotting principle
as OrderItem (see models/order.py).
"""
import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import GUID, pg_enum
from app.models.order import Order  # noqa: F401  (resolves relationship string)


class PaymentStatus(str, enum.Enum):
    CREATED = "created"  # Razorpay order created, customer hasn't paid yet
    PAID = "paid"  # signature verified (or webhook confirmed) successfully
    FAILED = "failed"
    REFUNDED = "refunded"


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )

    razorpay_order_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    razorpay_payment_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    razorpay_signature: Mapped[str | None] = mapped_column(String(255), nullable=True)

    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    status: Mapped[PaymentStatus] = mapped_column(
        pg_enum(PaymentStatus, name="payment_status"), default=PaymentStatus.CREATED, nullable=False, index=True
    )
    failure_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    order: Mapped["Order"] = relationship()
