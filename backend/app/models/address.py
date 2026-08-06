"""
Address table — one user can have many shipping/billing addresses.

DESIGN NOTES:
- user_id FK with ondelete="CASCADE": if a user is deleted, their addresses
  are automatically deleted by the DATABASE, not by application code. This
  is more reliable than "remember to delete addresses in the delete-user
  endpoint" — it holds even if someone deletes a row via a DB console.
- is_default: exactly one address per user should be the default shipping
  address at checkout. Enforced at the application layer in the service
  function (unset old default, set new one) rather than a DB constraint,
  since "at most one True per user_id" isn't expressible as a simple
  column constraint in Postgres without a partial unique index — which
  we'll add in Phase 2 when the addresses API is built.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import GUID


class Address(Base):
    __tablename__ = "addresses"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    label: Mapped[str] = mapped_column(String(50), default="Home")  # Home / Work / Other
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    phone_number: Mapped[str] = mapped_column(String(20), nullable=False)
    line1: Mapped[str] = mapped_column(String(255), nullable=False)
    line2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str] = mapped_column(String(100), nullable=False)
    postal_code: Mapped[str] = mapped_column(String(20), nullable=False)
    country: Mapped[str] = mapped_column(String(100), default="India")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="addresses")
