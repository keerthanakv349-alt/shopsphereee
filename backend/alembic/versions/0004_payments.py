"""payments

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-01

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

payment_status_enum = postgresql.ENUM("created", "paid", "failed", "refunded", name="payment_status")


def upgrade() -> None:
    payment_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "order_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("razorpay_order_id", sa.String(64), nullable=False),
        sa.Column("razorpay_payment_id", sa.String(64), nullable=True),
        sa.Column("razorpay_signature", sa.String(255), nullable=True),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("currency", sa.String(10), server_default="INR"),
        sa.Column(
            "status",
            postgresql.ENUM("created", "paid", "failed", "refunded", name="payment_status", create_type=False),
            nullable=False,
            server_default="created",
        ),
        sa.Column("failure_reason", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_payments_order_id", "payments", ["order_id"])
    op.create_index("ix_payments_razorpay_order_id", "payments", ["razorpay_order_id"], unique=True)
    op.create_index("ix_payments_status", "payments", ["status"])


def downgrade() -> None:
    op.drop_table("payments")
    payment_status_enum.drop(op.get_bind(), checkfirst=True)
