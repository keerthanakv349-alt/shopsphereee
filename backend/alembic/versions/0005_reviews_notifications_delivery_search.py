"""reviews, notifications, delivery tracking, search log

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-01

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

notification_type_enum = postgresql.ENUM("order_update", "payment_update", "general", name="notification_type")
tracking_status_enum = postgresql.ENUM(
    "order_packed", "shipped", "in_transit", "out_for_delivery", "delivered", name="tracking_status"
)


def upgrade() -> None:
    notification_type_enum.create(op.get_bind(), checkfirst=True)
    tracking_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "product_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(150), nullable=True),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("is_verified_purchase", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("helpful_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_reported", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("product_id", "user_id", name="uq_review_product_user"),
    )
    op.create_index("ix_reviews_product_id", "reviews", ["product_id"])

    op.create_table(
        "notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "notification_type",
            postgresql.ENUM("order_update", "payment_update", "general", name="notification_type", create_type=False),
            nullable=False,
            server_default="general",
        ),
        sa.Column("title", sa.String(150), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "related_order_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("orders.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])

    op.create_table(
        "delivery_partners",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("phone_number", sa.String(20), nullable=False),
        sa.Column("vehicle_number", sa.String(30), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "tracking_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "delivery_partner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("delivery_partners.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "status",
            postgresql.ENUM(
                "order_packed", "shipped", "in_transit", "out_for_delivery", "delivered",
                name="tracking_status", create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("location_label", sa.String(150), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_tracking_events_order_id", "tracking_events", ["order_id"])

    op.create_table(
        "search_queries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("query_text", sa.String(200), nullable=False),
        sa.Column("search_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_searched_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_search_queries_query_text", "search_queries", ["query_text"], unique=True)


def downgrade() -> None:
    op.drop_table("search_queries")
    op.drop_table("tracking_events")
    op.drop_table("delivery_partners")
    op.drop_table("notifications")
    op.drop_table("reviews")
    tracking_status_enum.drop(op.get_bind(), checkfirst=True)
    notification_type_enum.drop(op.get_bind(), checkfirst=True)
