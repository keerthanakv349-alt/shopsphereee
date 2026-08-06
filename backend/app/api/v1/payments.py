"""
Payment endpoints.

--- THE FULL PAYMENT FLOW, STEP BY STEP ---

1. Customer finishes checkout (POST /api/v1/orders from Phase 3) — an
   Order exists with status PENDING, but nothing has been paid yet.

2. Frontend calls POST /payments/razorpay/orders with the order_id. We:
   - verify the order belongs to the current user and hasn't already
     been paid (no existing PAID Payment row for it)
   - call gateway.create_order() — a real network call to Razorpay,
     asking THEM to create an order on their side (this is a Razorpay
     concept distinct from our own Order — every payment needs a
     matching Razorpay-side order for their Checkout widget to attach to)
   - save a Payment row locally with status=CREATED and their
     razorpay_order_id, so we have a record even if the customer never
     completes payment
   - return {razorpay_order_id, amount, currency, key_id} — everything
     the frontend needs to open Razorpay's Checkout widget

3. The customer pays in Razorpay's widget (entirely on Razorpay's
   servers — we never see card details, which is the whole point of
   using a payment gateway instead of handling cards ourselves).

4. On success, the widget calls our frontend back with
   {razorpay_order_id, razorpay_payment_id, razorpay_signature}. The
   frontend immediately POSTs that to /payments/razorpay/verify.

5. We recompute the expected signature ourselves (pure HMAC, see
   core/razorpay_gateway.py) and compare. Only if it matches do we mark
   the Payment PAID. This is the step that actually proves the payment
   happened — steps 3-4 alone are just "the browser said so."

6. INDEPENDENTLY, Razorpay also calls our webhook endpoint
   server-to-server (POST /payments/razorpay/webhook) with the same
   payment event. This is the AUTHORITATIVE confirmation — no browser
   in the middle to trust. In production, the webhook is what you'd
   actually rely on if the two ever disagreed (e.g. the customer closed
   their browser tab right after paying, before step 4 could fire — the
   webhook is what saves you from marking that order as unpaid forever).
"""
import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user, get_razorpay_gateway, require_role
from app.core.notifications import notify_user
from app.core.rate_limit import PAYMENT_RATE_LIMIT, limiter
from app.core.razorpay_gateway import RazorpayGateway, verify_payment_signature, verify_webhook_signature
from app.db.session import get_db
from app.models.notification import NotificationType
from app.models.order import Order, OrderStatus
from app.models.payment import Payment, PaymentStatus
from app.models.user import User, UserRole
from app.schemas.payment import (
    CreateRazorpayOrderRequest,
    CreateRazorpayOrderResponse,
    PaymentOut,
    RefundRequest,
    VerifyPaymentRequest,
)

router = APIRouter(prefix="/api/v1/payments", tags=["payments"])
admin_only = require_role(UserRole.ADMIN, UserRole.SUPER_ADMIN)


def _rupees_to_paise(amount: Decimal) -> int:
    return int(amount * 100)


@router.post("/razorpay/orders", response_model=CreateRazorpayOrderResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(PAYMENT_RATE_LIMIT)
def create_razorpay_order(
    request: Request,
    payload: CreateRazorpayOrderRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    gateway: RazorpayGateway = Depends(get_razorpay_gateway),
):
    order = (
        db.query(Order).filter(Order.id == payload.order_id, Order.user_id == current_user.id).first()
    )
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    if order.status not in (OrderStatus.PENDING,):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This order is not awaiting payment")

    already_paid = (
        db.query(Payment)
        .filter(Payment.order_id == order.id, Payment.status == PaymentStatus.PAID)
        .first()
    )
    if already_paid:
        raise HTTPException(status.HTTP_409_CONFLICT, "This order has already been paid")

    amount_paise = _rupees_to_paise(order.total_amount)
    razorpay_order = gateway.create_order(
        amount_paise=amount_paise, currency="INR", receipt=order.order_number
    )

    payment = Payment(
        order_id=order.id,
        razorpay_order_id=razorpay_order["id"],
        amount=order.total_amount,
        currency="INR",
        status=PaymentStatus.CREATED,
    )
    db.add(payment)
    db.commit()

    return CreateRazorpayOrderResponse(
        razorpay_order_id=razorpay_order["id"],
        amount=amount_paise,
        currency="INR",
        key_id=_get_key_id(),
    )


def _get_key_id() -> str:
    from app.core.config import settings

    return settings.RAZORPAY_KEY_ID


@router.post("/razorpay/verify", response_model=PaymentOut)
async def verify_razorpay_payment(
    payload: VerifyPaymentRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    payment = (
        db.query(Payment)
        .join(Order, Payment.order_id == Order.id)
        .filter(Payment.razorpay_order_id == payload.razorpay_order_id, Order.user_id == current_user.id)
        .first()
    )
    if payment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found")

    is_valid = verify_payment_signature(
        payload.razorpay_order_id, payload.razorpay_payment_id, payload.razorpay_signature
    )
    if not is_valid:
        payment.status = PaymentStatus.FAILED
        payment.failure_reason = "Signature verification failed"
        db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Payment verification failed")

    payment.status = PaymentStatus.PAID
    payment.razorpay_payment_id = payload.razorpay_payment_id
    payment.razorpay_signature = payload.razorpay_signature
    db.commit()
    db.refresh(payment)

    await notify_user(
        db,
        user_id=current_user.id,
        title="Payment received",
        message=f"We've received your payment of ₹{payment.amount}.",
        notification_type=NotificationType.PAYMENT_UPDATE,
        related_order_id=payment.order_id,
    )

    return payment


@router.post("/razorpay/webhook", status_code=status.HTTP_200_OK)
async def razorpay_webhook(request: Request, db: Session = Depends(get_db)):
    # Signature is computed over the exact raw request bytes — this MUST
    # read the raw body, not a parsed/re-serialized JSON dict, or the
    # signature will never match (whitespace/key-order differences alone
    # would break it).
    raw_body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")

    if not verify_webhook_signature(raw_body, signature):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid webhook signature")

    import json

    event = json.loads(raw_body)
    event_type = event.get("event")
    payload_entity = event.get("payload", {}).get("payment", {}).get("entity", {})
    razorpay_order_id = payload_entity.get("order_id")

    if not razorpay_order_id:
        return {"status": "ignored"}

    payment = db.query(Payment).filter(Payment.razorpay_order_id == razorpay_order_id).first()
    if payment is None:
        return {"status": "ignored"}

    # Idempotent by design: webhooks can and do arrive more than once for
    # the same event (Razorpay retries on timeout) — re-processing an
    # already-PAID payment as PAID again is a safe no-op, not a bug.
    if event_type == "payment.captured":
        already_paid = payment.status == PaymentStatus.PAID
        payment.status = PaymentStatus.PAID
        payment.razorpay_payment_id = payload_entity.get("id")
        db.commit()
        if not already_paid:
            order = db.get(Order, payment.order_id)
            if order is not None:
                await notify_user(
                    db,
                    user_id=order.user_id,
                    title="Payment received",
                    message=f"We've received your payment of ₹{payment.amount}.",
                    notification_type=NotificationType.PAYMENT_UPDATE,
                    related_order_id=order.id,
                )
    elif event_type == "payment.failed":
        payment.status = PaymentStatus.FAILED
        payment.failure_reason = payload_entity.get("error_description", "Payment failed")
        db.commit()

    return {"status": "processed"}


@router.get("/order/{order_id}", response_model=list[PaymentOut])
def get_order_payments(
    order_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    order = db.query(Order).filter(Order.id == order_id, Order.user_id == current_user.id).first()
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    return db.query(Payment).filter(Payment.order_id == order_id).order_by(Payment.created_at.desc()).all()


@router.post("/{payment_id}/refund", response_model=PaymentOut, tags=["admin-payments"])
def refund_payment(
    payment_id: uuid.UUID,
    payload: RefundRequest,
    db: Session = Depends(get_db),
    _: User = Depends(admin_only),
    gateway: RazorpayGateway = Depends(get_razorpay_gateway),
):
    payment = db.get(Payment, payment_id)
    if payment is None or payment.status != PaymentStatus.PAID:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No paid payment found with this ID")

    refund_amount = payload.amount or payment.amount
    if refund_amount > payment.amount:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Refund amount cannot exceed the original payment")

    gateway.create_refund(payment.razorpay_payment_id, _rupees_to_paise(refund_amount))

    payment.status = PaymentStatus.REFUNDED
    order = db.get(Order, payment.order_id)
    if order is not None:
        order.status = OrderStatus.REFUNDED

    db.commit()
    db.refresh(payment)
    return payment


@router.get("/admin/all", response_model=list[PaymentOut], tags=["admin-payments"])
def admin_list_payments(db: Session = Depends(get_db), _: User = Depends(admin_only)):
    return db.query(Payment).order_by(Payment.created_at.desc()).all()
