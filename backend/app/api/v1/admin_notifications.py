from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.deps import require_role
from app.db.session import get_db
from app.models.catalog import ProductVariant
from app.models.order import Order
from app.models.payment import Payment, PaymentStatus
from app.models.user import User, UserRole
from app.schemas.admin import NotificationListResponse, NotificationOut

router = APIRouter(
    prefix="/api/v1/admin/notifications",
    tags=["admin-notifications"],
)

admin_only = require_role(UserRole.ADMIN, UserRole.SUPER_ADMIN)

LOW_STOCK_THRESHOLD = 5


@router.get("", response_model=NotificationListResponse)
def get_notifications(
    db: Session = Depends(get_db),
    _: User = Depends(admin_only),
):
    notifications: list[NotificationOut] = []

    # Recent Orders
    recent_orders = (
        db.query(Order)
        .order_by(Order.created_at.desc())
        .limit(5)
        .all()
    )

    for order in recent_orders:
        notifications.append(
            NotificationOut(
                title="New Order",
                message=f"Order {order.order_number} was placed.",
                type="order",
                created_at=order.created_at,
            )
        )

    # Recent Customers
    recent_users = (
        db.query(User)
        .filter(User.role == UserRole.CUSTOMER)
        .order_by(User.created_at.desc())
        .limit(5)
        .all()
    )

    for user in recent_users:
        notifications.append(
            NotificationOut(
                title="New Customer",
                message=f"{user.full_name} registered.",
                type="customer",
                created_at=user.created_at,
            )
        )

    # Successful Payments
    recent_payments = (
        db.query(Payment)
        .filter(Payment.status == PaymentStatus.PAID)
        .order_by(Payment.created_at.desc())
        .limit(5)
        .all()
    )

    for payment in recent_payments:
        notifications.append(
            NotificationOut(
                title="Payment Received",
                message=f"₹{payment.amount} received.",
                type="payment",
                created_at=payment.created_at,
            )
        )

    # Low Stock
    low_stock = (
        db.query(ProductVariant)
        .filter(ProductVariant.stock_quantity <= LOW_STOCK_THRESHOLD)
        .all()
    )

    for variant in low_stock:
        notifications.append(
            NotificationOut(
                title="Low Stock",
                message=f"{variant.sku} has only {variant.stock_quantity} left.",
                type="stock",
                created_at=datetime.utcnow(),
            )
        )

    notifications.sort(
        key=lambda x: x.created_at,
        reverse=True,
    )

    return NotificationListResponse(
        notifications=notifications
    )