"""
Razorpay integration boundary.

WHY THIS IS SPLIT INTO TWO KINDS OF CODE:

1. SIGNATURE VERIFICATION (verify_payment_signature, verify_webhook_signature)
   is pure, local HMAC-SHA256 computation — no network call. This is also
   the single most security-critical part of the entire payment flow: it's
   what proves a "payment succeeded" message actually came from Razorpay
   and wasn't forged by a malicious client hitting our API directly and
   claiming "trust me, I paid." Because it's pure computation, it's
   implemented for real here and genuinely unit-tested with real
   cryptographic math in tests/test_payments.py — nothing about it is
   mocked.

2. ACTUAL API CALLS (creating a Razorpay order, issuing a refund) require
   real network access to Razorpay's servers and real API credentials.
   Those live behind the RazorpayGateway Protocol below, injected via
   FastAPI's dependency system (see api/v1/deps.py's get_razorpay_gateway).
   Production wiring uses LiveRazorpayGateway (wraps the official
   `razorpay` SDK). The test suite overrides the dependency with a
   FakeRazorpayGateway (tests/conftest.py) that returns deterministic fake
   IDs — this is the standard, correct way to test code that talks to a
   third-party payment API: you test YOUR logic (does the right thing
   happen when create_order succeeds/fails) without actually hitting a
   real payment processor from a CI pipeline, which would be slow,
   flaky, cost real money on refunds, and require secrets in test config.
"""
import hashlib
import hmac
from typing import Protocol

import razorpay

from app.core.config import settings


class RazorpayGateway(Protocol):
    def create_order(self, amount_paise: int, currency: str, receipt: str) -> dict: ...
    def create_refund(self, razorpay_payment_id: str, amount_paise: int) -> dict: ...


class LiveRazorpayGateway:
    """Wraps the real `razorpay` SDK. Used in production. Never invoked by tests."""

    def __init__(self) -> None:
        self._client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))

    def create_order(self, amount_paise: int, currency: str, receipt: str) -> dict:
        return self._client.order.create(
            {
                "amount": amount_paise,
                "currency": currency,
                "receipt": receipt,
                "payment_capture": 1,  # auto-capture — funds settle without a separate capture call
            }
        )

    def create_refund(self, razorpay_payment_id: str, amount_paise: int) -> dict:
        return self._client.payment.refund(razorpay_payment_id, {"amount": amount_paise})


def verify_payment_signature(
    razorpay_order_id: str, razorpay_payment_id: str, razorpay_signature: str
) -> bool:
    """
    Razorpay's documented post-payment verification scheme:
        expected_signature = HMAC_SHA256(order_id + "|" + payment_id, key_secret)
    The frontend gets order_id/payment_id/signature back from the Razorpay
    Checkout widget after a successful payment and sends all three here.
    We recompute the signature ourselves from the order_id and payment_id
    — never trust the "it succeeded" claim without this check.
    """
    payload = f"{razorpay_order_id}|{razorpay_payment_id}"
    expected_signature = hmac.new(
        settings.RAZORPAY_KEY_SECRET.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()
    # Constant-time comparison — a naive `==` short-circuits on the first
    # mismatched byte, and the tiny timing difference is (in principle)
    # enough for an attacker to guess a valid signature byte by byte.
    return hmac.compare_digest(expected_signature, razorpay_signature)


def verify_webhook_signature(raw_body: bytes, received_signature: str) -> bool:
    """
    Webhooks are the AUTHORITATIVE source of payment status in production
    — they're sent server-to-server directly from Razorpay, so unlike the
    client-triggered /verify endpoint above, there's no browser in the
    middle that a compromised client could tamper with. Real systems treat
    the webhook as the source of truth and the client-side /verify call as
    a same-page UX nicety for showing an instant confirmation.
    """
    expected_signature = hmac.new(
        settings.RAZORPAY_WEBHOOK_SECRET.encode(), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected_signature, received_signature)
