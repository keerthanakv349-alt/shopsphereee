"""
User table — the root of the whole auth/identity system.

DESIGN NOTES (why these columns, specifically):
- id: UUID instead of auto-increment int. Production apps avoid sequential
  integer PKs for user-facing entities because they leak information
  (competitors/scrapers can guess "how many users do you have" or iterate
  ?id=1,2,3...). UUIDs are non-guessable.
- email: unique + indexed, since login is by email and we look it up on
  every login request — an index makes that O(log n) instead of a table scan.
- hashed_password: nullable, because a user who signs up via Google OAuth
  (Phase 2+) has no password at all.
- role: Enum, not a free-text string — the DB itself rejects invalid roles,
  not just the API layer. This matters because multiple services /
  future admin scripts might write to this table directly.
- is_active: soft "disable this account" flag, used for banning without
  deleting data (deleting a user would orphan their orders/reviews).
- is_email_verified: gates certain actions (e.g. checkout) until the user
  proves they own the email — reduces fake accounts and fraud.
- created_at/updated_at: every production table has these for auditing,
  debugging, and "sort by newest" queries — added on virtually every table.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import GUID, pg_enum
from app.models.address import Address  # noqa: F401  (needed to resolve relationship string)


class UserRole(str, enum.Enum):
    CUSTOMER = "customer"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(), primary_key=True, default=uuid.uuid4
    )
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone_number: Mapped[str | None] = mapped_column(String(20), nullable=True)

    role: Mapped[UserRole] = mapped_column(
        pg_enum(UserRole, name="user_role"), default=UserRole.CUSTOMER, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    addresses: Mapped[list["Address"]] = relationship(back_populates="user", cascade="all, delete-orphan")
