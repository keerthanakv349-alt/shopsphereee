"""
Catalog tables: Category, Brand, Product, ProductVariant, ProductImage.

DESIGN NOTES — why the schema is shaped this way:

- Product itself has NO price the customer actually pays and NO stock
  count. Those live on ProductVariant. This mirrors how Myntra/Amazon
  actually work: "Nike Air Max 90" is one Product, but "Nike Air Max 90,
  size UK9, Black" is a distinct SKU with its own stock and (optionally)
  its own price. If Product carried price/stock directly, a shoe with 5
  sizes and 3 colors couldn't be modeled without either duplicating the
  whole Product row per size/color, or bolting on a parallel table anyway
  — so we start with the variant table from day one instead of migrating
  into it later under production data.

- ProductVariant.price_override is nullable: most variants just use the
  product's base_price, but some (e.g. a plus size, or a limited colorway)
  cost more — override only where it actually differs, don't duplicate
  the price on every variant by default.

- Inventory is folded into ProductVariant.stock_quantity for Phase 2
  rather than a separate Inventory table. A dedicated Inventory table
  earns its keep once you have multiple warehouses / reservation logic
  (stock reserved during checkout before payment confirms) — that's a
  Phase 3+ concern when Orders exist. Introducing it now would be an
  unused table with no consumer, which is exactly the kind of premature
  abstraction production codebases try to avoid.

- ProductImage.variant_id is nullable: most images belong to the product
  as a whole (front/back/detail shots), but color variants often need
  their OWN image (a red shoe photographs differently than a blue one).
  Nullable FK lets one images table serve both cases instead of two
  near-identical tables.

- Category.parent_id (self-referential FK) models a category tree
  ("Men > Footwear > Sneakers") with a single table instead of a fixed
  number of nesting-level columns, which would break the moment the
  business wants a 4th level.

- Product.status is an enum (draft/active/inactive), not a boolean
  is_visible. Admins need a "saved but not yet live" state (draft) that's
  distinct from "was live, now pulled" (inactive) — a single boolean
  can't tell those apart, and reporting/analytics care about the
  difference.
"""
import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import GUID, pg_enum


class ProductStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    INACTIVE = "inactive"


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    products: Mapped[list["Product"]] = relationship(back_populates="category")


class Brand(Base):
    __tablename__ = "brands"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    products: Mapped[list["Product"]] = relationship(back_populates="brand")


class Product(Base):
    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(220), unique=True, index=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")

    category_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    brand_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("brands.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    base_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    discount_percentage: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0"))
    gst_percentage: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0"))

    status: Mapped[ProductStatus] = mapped_column(
        pg_enum(ProductStatus, name="product_status"), default=ProductStatus.DRAFT, nullable=False, index=True
    )
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False)
    is_trending: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    category: Mapped["Category"] = relationship(back_populates="products")
    brand: Mapped["Brand"] = relationship(back_populates="products")
    variants: Mapped[list["ProductVariant"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    images: Mapped[list["ProductImage"]] = relationship(
        back_populates="product", cascade="all, delete-orphan", order_by="ProductImage.display_order"
    )

    @property
    def primary_image_url(self) -> str | None:
        """Used by ProductOut (list schema) — not a DB column, just a
        convenience accessor so the API doesn't force the frontend to
        pick an image out of the full array on every grid card."""
        if not self.images:
            return None
        primary = next((img for img in self.images if img.is_primary), None)
        return (primary or self.images[0]).image_url


class ProductVariant(Base):
    __tablename__ = "product_variants"
    __table_args__ = (UniqueConstraint("sku", name="uq_variant_sku"),)

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )

    sku: Mapped[str] = mapped_column(String(64), nullable=False)
    size: Mapped[str | None] = mapped_column(String(20), nullable=True)
    color: Mapped[str | None] = mapped_column(String(40), nullable=True)
    stock_quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    price_override: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    product: Mapped["Product"] = relationship(back_populates="variants")


class ProductImage(Base):
    __tablename__ = "product_images"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("product_variants.id", ondelete="CASCADE"), nullable=True
    )

    image_url: Mapped[str] = mapped_column(String(500), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    product: Mapped["Product"] = relationship(back_populates="images")
