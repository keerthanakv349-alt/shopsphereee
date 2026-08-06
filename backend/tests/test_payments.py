import hashlib
import hmac
import json

from app.core.config import settings
from app.core.razorpay_gateway import verify_payment_signature, verify_webhook_signature
from app.models.user import UserRole
from tests.conftest import TestingSessionLocal


def _make_admin(client, email="admin@example.com"):
    signup = client.post(
        "/api/v1/auth/signup",
        json={"full_name": "Admin User", "email": email, "password": "Passw0rd!"},
    )
    access_token = signup.json()["tokens"]["access_token"]
    user_id = signup.json()["user"]["id"]

    from app.models.user import User

    session = TestingSessionLocal()
    user = session.get(User, user_id)
    user.role = UserRole.ADMIN
    session.commit()
    session.close()

    return {"Authorization": f"Bearer {access_token}"}


def _make_customer(client, email="customer@example.com"):
    signup = client.post(
        "/api/v1/auth/signup",
        json={"full_name": "Customer One", "email": email, "password": "Passw0rd!"},
    )
    return {"Authorization": f"Bearer {signup.json()['tokens']['access_token']}"}


def _make_paid_order(client, admin, customer, price="1000.00"):
    """Full setup: product, address, cart, checkout — returns the created order."""
    category = client.post("/api/v1/admin/categories", json={"name": "Electronics"}, headers=admin).json()
    brand = client.post("/api/v1/admin/brands", json={"name": "Sony"}, headers=admin).json()
    product = client.post(
        "/api/v1/admin/products",
        json={
            "name": "Headphones",
            "category_id": category["id"],
            "brand_id": brand["id"],
            "base_price": price,
            "gst_percentage": "0",
            "status": "active",
            "variants": [{"sku": "HP-1", "stock_quantity": 5}],
        },
        headers=admin,
    ).json()
    address = client.post(
        "/api/v1/addresses",
        json={
            "full_name": "Jane Doe",
            "phone_number": "9999999999",
            "line1": "123 MG Road",
            "city": "Bengaluru",
            "state": "Karnataka",
            "postal_code": "560001",
        },
        headers=customer,
    ).json()
    client.post(
        "/api/v1/cart/items", json={"variant_id": product["variants"][0]["id"], "quantity": 1}, headers=customer
    )
    order = client.post(
        "/api/v1/orders", json={"address_id": address["id"], "shipping_charge": "0"}, headers=customer
    ).json()
    return order


# --- Pure signature verification (real HMAC math, no network, no mocking) ---
def test_valid_payment_signature_accepted():
    order_id, payment_id = "order_abc123", "pay_xyz789"
    payload = f"{order_id}|{payment_id}"
    correct_signature = hmac.new(
        settings.RAZORPAY_KEY_SECRET.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()

    assert verify_payment_signature(order_id, payment_id, correct_signature) is True


def test_tampered_payment_signature_rejected():
    order_id, payment_id = "order_abc123", "pay_xyz789"
    wrong_signature = "0" * 64  # well-formed hex, but not the real HMAC
    assert verify_payment_signature(order_id, payment_id, wrong_signature) is False


def test_signature_for_different_payment_id_rejected():
    # Proves the signature is bound to the SPECIFIC order+payment pair —
    # a signature valid for one payment must not validate a different one.
    order_id = "order_abc123"
    payload = f"{order_id}|pay_original"
    signature = hmac.new(settings.RAZORPAY_KEY_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()

    assert verify_payment_signature(order_id, "pay_original", signature) is True
    assert verify_payment_signature(order_id, "pay_different", signature) is False


def test_webhook_signature_verification():
    body = json.dumps({"event": "payment.captured"}).encode()
    correct_signature = hmac.new(settings.RAZORPAY_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()

    assert verify_webhook_signature(body, correct_signature) is True
    assert verify_webhook_signature(body, "wrong" * 16) is False
    # Even a single-byte change to the body must invalidate the signature.
    assert verify_webhook_signature(body + b" ", correct_signature) is False


# --- Full flow through the API (fake gateway, real signature verification) ---
def test_create_razorpay_order_for_own_order(client):
    admin = _make_admin(client)
    customer = _make_customer(client)
    order = _make_paid_order(client, admin, customer)

    resp = client.post("/api/v1/payments/razorpay/orders", json={"order_id": order["id"]}, headers=customer)
    assert resp.status_code == 201
    body = resp.json()
    assert body["razorpay_order_id"].startswith("order_fake")
    assert body["amount"] == 100000  # 1000.00 rupees -> 100000 paise
    assert body["key_id"] == settings.RAZORPAY_KEY_ID


def test_cannot_create_razorpay_order_for_someone_elses_order(client):
    admin = _make_admin(client)
    alice = _make_customer(client, "alice@example.com")
    bob = _make_customer(client, "bob@example.com")
    order = _make_paid_order(client, admin, alice)

    resp = client.post("/api/v1/payments/razorpay/orders", json={"order_id": order["id"]}, headers=bob)
    assert resp.status_code == 404


def test_full_verify_flow_marks_payment_paid(client):
    admin = _make_admin(client)
    customer = _make_customer(client)
    order = _make_paid_order(client, admin, customer)

    create_resp = client.post(
        "/api/v1/payments/razorpay/orders", json={"order_id": order["id"]}, headers=customer
    ).json()
    razorpay_order_id = create_resp["razorpay_order_id"]
    razorpay_payment_id = "pay_test123456"

    payload = f"{razorpay_order_id}|{razorpay_payment_id}"
    valid_signature = hmac.new(
        settings.RAZORPAY_KEY_SECRET.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()

    verify_resp = client.post(
        "/api/v1/payments/razorpay/verify",
        json={
            "razorpay_order_id": razorpay_order_id,
            "razorpay_payment_id": razorpay_payment_id,
            "razorpay_signature": valid_signature,
        },
        headers=customer,
    )
    assert verify_resp.status_code == 200
    assert verify_resp.json()["status"] == "paid"

    history = client.get(f"/api/v1/payments/order/{order['id']}", headers=customer).json()
    assert history[0]["status"] == "paid"


def test_forged_signature_rejected_and_marks_failed(client):
    admin = _make_admin(client)
    customer = _make_customer(client)
    order = _make_paid_order(client, admin, customer)

    create_resp = client.post(
        "/api/v1/payments/razorpay/orders", json={"order_id": order["id"]}, headers=customer
    ).json()

    forged_resp = client.post(
        "/api/v1/payments/razorpay/verify",
        json={
            "razorpay_order_id": create_resp["razorpay_order_id"],
            "razorpay_payment_id": "pay_fake",
            "razorpay_signature": "a" * 64,  # attacker just made this up
        },
        headers=customer,
    )
    assert forged_resp.status_code == 400

    history = client.get(f"/api/v1/payments/order/{order['id']}", headers=customer).json()
    assert history[0]["status"] == "failed"


def test_cannot_pay_for_already_paid_order(client):
    admin = _make_admin(client)
    customer = _make_customer(client)
    order = _make_paid_order(client, admin, customer)

    create_resp = client.post(
        "/api/v1/payments/razorpay/orders", json={"order_id": order["id"]}, headers=customer
    ).json()
    payload = f"{create_resp['razorpay_order_id']}|pay_1"
    signature = hmac.new(settings.RAZORPAY_KEY_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    client.post(
        "/api/v1/payments/razorpay/verify",
        json={
            "razorpay_order_id": create_resp["razorpay_order_id"],
            "razorpay_payment_id": "pay_1",
            "razorpay_signature": signature,
        },
        headers=customer,
    )

    second_attempt = client.post(
        "/api/v1/payments/razorpay/orders", json={"order_id": order["id"]}, headers=customer
    )
    assert second_attempt.status_code == 409


# --- Webhook ---
def test_webhook_updates_payment_status(client):
    admin = _make_admin(client)
    customer = _make_customer(client)
    order = _make_paid_order(client, admin, customer)
    create_resp = client.post(
        "/api/v1/payments/razorpay/orders", json={"order_id": order["id"]}, headers=customer
    ).json()

    event_body = json.dumps(
        {
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {"id": "pay_webhook_1", "order_id": create_resp["razorpay_order_id"]}
                }
            },
        }
    ).encode()
    signature = hmac.new(settings.RAZORPAY_WEBHOOK_SECRET.encode(), event_body, hashlib.sha256).hexdigest()

    resp = client.post(
        "/api/v1/payments/razorpay/webhook",
        content=event_body,
        headers={"X-Razorpay-Signature": signature, "Content-Type": "application/json"},
    )
    assert resp.status_code == 200

    history = client.get(f"/api/v1/payments/order/{order['id']}", headers=customer).json()
    assert history[0]["status"] == "paid"
    assert history[0]["razorpay_payment_id"] == "pay_webhook_1"


def test_webhook_with_bad_signature_rejected(client):
    resp = client.post(
        "/api/v1/payments/razorpay/webhook",
        content=b'{"event": "payment.captured"}',
        headers={"X-Razorpay-Signature": "wrong"},
    )
    assert resp.status_code == 400


# --- Refunds (admin only) ---
def test_admin_can_refund_paid_payment(client):
    admin = _make_admin(client)
    customer = _make_customer(client)
    order = _make_paid_order(client, admin, customer)
    create_resp = client.post(
        "/api/v1/payments/razorpay/orders", json={"order_id": order["id"]}, headers=customer
    ).json()
    payload = f"{create_resp['razorpay_order_id']}|pay_refund_test"
    signature = hmac.new(settings.RAZORPAY_KEY_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    verify_resp = client.post(
        "/api/v1/payments/razorpay/verify",
        json={
            "razorpay_order_id": create_resp["razorpay_order_id"],
            "razorpay_payment_id": "pay_refund_test",
            "razorpay_signature": signature,
        },
        headers=customer,
    ).json()

    refund_resp = client.post(f"/api/v1/payments/{verify_resp['id']}/refund", json={}, headers=admin)
    assert refund_resp.status_code == 200
    assert refund_resp.json()["status"] == "refunded"

    order_check = client.get(f"/api/v1/orders/{order['id']}", headers=customer).json()
    assert order_check["status"] == "refunded"


def test_customer_cannot_refund(client):
    admin = _make_admin(client)
    customer = _make_customer(client)
    order = _make_paid_order(client, admin, customer)
    create_resp = client.post(
        "/api/v1/payments/razorpay/orders", json={"order_id": order["id"]}, headers=customer
    ).json()

    resp = client.post(f"/api/v1/payments/{create_resp['razorpay_order_id']}/refund", json={}, headers=customer)
    assert resp.status_code == 403


def test_admin_payment_listing(client):
    admin = _make_admin(client)
    customer = _make_customer(client)
    _make_paid_order(client, admin, customer)

    resp = client.get("/api/v1/payments/admin/all", headers=admin)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
