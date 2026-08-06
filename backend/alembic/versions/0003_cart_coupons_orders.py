"""cart, coupons, orders

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-01

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

discount_type_enum = postgresql.ENUM("percentage", "flat", name="discount_type")
order_status_enum = postgresql.ENUM(
    "pending", "packed", "shipped", "out_for_delivery", "delivered", "cancelled", "returned", "refunded",
    name="order_status",
)


def upgrade() -> None:
    discount_type_enum.create(op.get_bind(), checkfirst=True)
    order_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "carts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("applied_coupon_code", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "cart_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "cart_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("carts.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "variant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("product_variants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("cart_id", "variant_id", name="uq_cart_variant"),
    )
    op.create_index("ix_cart_items_cart_id", "cart_items", ["cart_id"])

    op.create_table(
        "coupons",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column(
            "discount_type",
            postgresql.ENUM("percentage", "flat", name="discount_type", create_type=False),
            nullable=False,
        ),
        sa.Column("discount_value", sa.Numeric(10, 2), nullable=False),
        sa.Column("max_discount_amount", sa.Numeric(10, 2), nullable=True),
        sa.Column("min_order_value", sa.Numeric(10, 2), server_default="0"),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("usage_limit", sa.Integer(), nullable=True),
        sa.Column("times_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_coupons_code", "coupons", ["code"], unique=True)

    op.create_table(
        "orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("order_number", sa.String(30), nullable=False),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "status",
            postgresql.ENUM(
                "pending", "packed", "shipped", "out_for_delivery", "delivered", "cancelled", "returned",
                "refunded", name="order_status", create_type=False,
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("subtotal", sa.Numeric(10, 2), nullable=False),
        sa.Column("discount_amount", sa.Numeric(10, 2), server_default="0"),
        sa.Column("gst_amount", sa.Numeric(10, 2), server_default="0"),
        sa.Column("shipping_charge", sa.Numeric(10, 2), server_default="0"),
        sa.Column("total_amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("coupon_code", sa.String(50), nullable=True),
        sa.Column("shipping_full_name", sa.String(120), nullable=False),
        sa.Column("shipping_phone_number", sa.String(20), nullable=False),
        sa.Column("shipping_line1", sa.String(255), nullable=False),
        sa.Column("shipping_line2", sa.String(255), nullable=True),
        sa.Column("shipping_city", sa.String(100), nullable=False),
        sa.Column("shipping_state", sa.String(100), nullable=False),
        sa.Column("shipping_postal_code", sa.String(20), nullable=False),
        sa.Column("shipping_country", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_orders_order_number", "orders", ["order_number"], unique=True)
    op.create_index("ix_orders_user_id", "orders", ["user_id"])
    op.create_index("ix_orders_status", "orders", ["status"])

    op.create_table(
        "order_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "order_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "product_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column(
            "variant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("product_variants.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("product_name", sa.String(200), nullable=False),
        sa.Column("sku", sa.String(64), nullable=False),
        sa.Column("size", sa.String(20), nullable=True),
        sa.Column("color", sa.String(40), nullable=True),
        sa.Column("unit_price", sa.Numeric(10, 2), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("line_total", sa.Numeric(10, 2), nullable=False),
    )
    op.create_index("ix_order_items_order_id", "order_items", ["order_id"])


def downgrade() -> None:
    op.drop_table("order_items")
    op.drop_table("orders")
    op.drop_table("coupons")
    op.drop_table("cart_items")
    op.drop_table("carts")
    order_status_enum.drop(op.get_bind(), checkfirst=True)
    discount_type_enum.drop(op.get_bind(), checkfirst=True)
