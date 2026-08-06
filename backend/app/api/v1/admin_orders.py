"""
Admin order management.

WHY STATUS TRANSITIONS ARE VALIDATED (not just "set status = whatever the
admin sent"): letting an order jump straight from 'pending' to 'delivered'
skips real-world steps that other systems depend on (a 'shipped' webhook
is what would trigger a tracking-number email in Phase 6, for instance).
_FORWARD_TRANSITIONS encodes the same lifecycle diagram from the brief —
pending → packed → shipped → out_for_delivery → delivered, with
cancellation only possible before shipping, and returns/refunds only
after delivery — as data the endpoint checks, rather than trusting every
caller to send transitions in the right order.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, selectinload

from app.api.v1.deps import require_role
from app.core.notifications import notify_user
from app.db.session import get_db
from app.models.notification import NotificationType
from app.models.order import Order, OrderStatus
from app.models.user import User, UserRole
from app.schemas.order import OrderOut, OrderStatusUpdate

router = APIRouter(prefix="/api/v1/admin/orders", tags=["admin-orders"])
admin_only = require_role(UserRole.ADMIN, UserRole.SUPER_ADMIN)

_FORWARD_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.PENDING: {OrderStatus.PACKED, OrderStatus.CANCELLED},
    OrderStatus.PACKED: {OrderStatus.SHIPPED, OrderStatus.CANCELLED},
    OrderStatus.SHIPPED: {OrderStatus.OUT_FOR_DELIVERY},
    OrderStatus.OUT_FOR_DELIVERY: {OrderStatus.DELIVERED},
    OrderStatus.DELIVERED: {OrderStatus.RETURNED},
    OrderStatus.RETURNED: {OrderStatus.REFUNDED},
    OrderStatus.CANCELLED: set(),
    OrderStatus.REFUNDED: set(),
}


@router.get("", response_model=list[OrderOut])
def admin_list_orders(db: Session = Depends(get_db), _: User = Depends(admin_only)):
    return db.query(Order).options(selectinload(Order.items)).order_by(Order.created_at.desc()).all()


@router.put("/{order_id}/status", response_model=OrderOut)
async def admin_update_order_status(
    order_id: uuid.UUID,
    payload: OrderStatusUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(admin_only),
):
    order = db.query(Order).filter(Order.id == order_id).options(selectinload(Order.items)).first()
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")

    allowed_next = _FORWARD_TRANSITIONS.get(order.status, set())
    if payload.status not in allowed_next:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Cannot move an order from '{order.status.value}' to '{payload.status.value}'",
        )

    order.status = payload.status
    db.commit()
    db.refresh(order)

    await notify_user(
        db,
        user_id=order.user_id,
        title=f"Order {order.order_number} update",
        message=f"Your order is now: {payload.status.value.replace('_', ' ')}",
        notification_type=NotificationType.ORDER_UPDATE,
        related_order_id=order.id,
    )

    return order
