"""
Admin dashboard summary.

WHY total_revenue COMES FROM Payment, NOT Order.total_amount:
An Order can exist without ever being paid (abandoned at checkout,
payment failed and never retried) — summing Order.total_amount would
count revenue that was never actually collected. Payment rows with
status=PAID are the ground truth for money that has actually changed
hands, same principle as why Payment is its own table at all (see
models/payment.py).

WHY LOW-STOCK IS A FIXED THRESHOLD HERE, NOT CONFIGURABLE:
A real system would let admins set a per-product or per-category
reorder threshold (Settings module — out of scope for this phase). A
single constant is enough to demonstrate the concept without building
a whole configuration UI for one number.
"""
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.v1.deps import require_role
from app.db.session import get_db
from app.models.catalog import Product, ProductStatus, ProductVariant
from app.models.order import Order
from app.models.payment import Payment, PaymentStatus
from app.models.user import User, UserRole
from app.schemas.admin import DashboardSummary

router = APIRouter(prefix="/api/v1/admin/dashboard", tags=["admin-dashboard"])
admin_only = require_role(UserRole.ADMIN, UserRole.SUPER_ADMIN)

LOW_STOCK_THRESHOLD = 5


@router.get("/summary", response_model=DashboardSummary)
def get_dashboard_summary(db: Session = Depends(get_db), _: User = Depends(admin_only)):
    total_revenue = (
        db.query(func.coalesce(func.sum(Payment.amount), 0))
        .filter(Payment.status == PaymentStatus.PAID)
        .scalar()
    )
    total_orders = db.query(func.count(Order.id)).scalar()
    total_customers = db.query(func.count(User.id)).filter(User.role == UserRole.CUSTOMER).scalar()
    total_products = (
        db.query(func.count(Product.id)).filter(Product.status == ProductStatus.ACTIVE).scalar()
    )
    low_stock_variant_count = (
        db.query(func.count(ProductVariant.id))
        .filter(ProductVariant.stock_quantity <= LOW_STOCK_THRESHOLD)
        .scalar()
    )

    recent_orders = (
        db.execute(
            select(Order).options(selectinload(Order.items)).order_by(Order.created_at.desc()).limit(5)
        )
        .scalars()
        .all()
    )

    return DashboardSummary(
        total_revenue=Decimal(total_revenue),
        total_orders=total_orders,
        total_customers=total_customers,
        total_products=total_products,
        low_stock_variant_count=low_stock_variant_count,
        recent_orders=recent_orders,
    )
