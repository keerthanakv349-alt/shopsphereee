import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.payment import PaymentStatus


class CreateRazorpayOrderRequest(BaseModel):
    order_id: uuid.UUID


class CreateRazorpayOrderResponse(BaseModel):
    razorpay_order_id: str
    amount: int  # paise — what the Razorpay Checkout widget expects
    currency: str
    key_id: str  # public key; safe to expose to the frontend


class VerifyPaymentRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class RefundRequest(BaseModel):
    # Optional partial refund amount in rupees; omit for a full refund.
    amount: Decimal | None = Field(default=None, gt=0)


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    order_id: uuid.UUID
    razorpay_order_id: str
    razorpay_payment_id: str | None
    amount: Decimal
    currency: str
    status: PaymentStatus
    failure_reason: str | None
    created_at: datetime
