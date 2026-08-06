"""catalog: categories, brands, products, variants, images

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-01

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

product_status_enum = postgresql.ENUM("draft", "active", "inactive", name="product_status")


def upgrade() -> None:
    product_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("slug", sa.String(120), nullable=False),
        sa.Column(
            "parent_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("categories.id", ondelete="SET NULL")
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_categories_slug", "categories", ["slug"], unique=True)

    op.create_table(
        "brands",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("slug", sa.String(120), nullable=False),
        sa.Column("logo_url", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_brands_slug", "brands", ["slug"], unique=True)

    op.create_table(
        "products",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(220), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "category_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("categories.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "brand_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("brands.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("base_price", sa.Numeric(10, 2), nullable=False),
        sa.Column("discount_percentage", sa.Numeric(5, 2), server_default="0"),
        sa.Column("gst_percentage", sa.Numeric(5, 2), server_default="0"),
        sa.Column(
            "status",
            postgresql.ENUM("draft", "active", "inactive", name="product_status", create_type=False),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("is_featured", sa.Boolean(), server_default=sa.false()),
        sa.Column("is_trending", sa.Boolean(), server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_products_slug", "products", ["slug"], unique=True)
    op.create_index("ix_products_category_id", "products", ["category_id"])
    op.create_index("ix_products_brand_id", "products", ["brand_id"])
    op.create_index("ix_products_status", "products", ["status"])

    op.create_table(
        "product_variants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "product_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sku", sa.String(64), nullable=False),
        sa.Column("size", sa.String(20), nullable=True),
        sa.Column("color", sa.String(40), nullable=True),
        sa.Column("stock_quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("price_override", sa.Numeric(10, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("sku", name="uq_variant_sku"),
    )
    op.create_index("ix_product_variants_product_id", "product_variants", ["product_id"])

    op.create_table(
        "product_images",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "product_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "variant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("product_variants.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("image_url", sa.String(500), nullable=False),
        sa.Column("is_primary", sa.Boolean(), server_default=sa.false()),
        sa.Column("display_order", sa.Integer(), server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_product_images_product_id", "product_images", ["product_id"])


def downgrade() -> None:
    op.drop_table("product_images")
    op.drop_table("product_variants")
    op.drop_table("products")
    op.drop_table("brands")
    op.drop_table("categories")
    product_status_enum.drop(op.get_bind(), checkfirst=True)
