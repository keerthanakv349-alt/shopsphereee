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


def _make_product(client, admin_headers, stock=10, price="1000.00", discount="0", gst="12"):
    category = client.post("/api/v1/admin/categories", json={"name": "Apparel"}, headers=admin_headers).json()
    brand = client.post("/api/v1/admin/brands", json={"name": "Puma"}, headers=admin_headers).json()
    product = client.post(
        "/api/v1/admin/products",
        json={
            "name": "Checkout Test Tee",
            "category_id": category["id"],
            "brand_id": brand["id"],
            "base_price": price,
            "discount_percentage": discount,
            "gst_percentage": gst,
            "status": "active",
            "variants": [{"sku": "TEE-M", "size": "M", "stock_quantity": stock}],
        },
        headers=admin_headers,
    ).json()
    return product


def _make_address(client, customer_headers):
    return client.post(
        "/api/v1/addresses",
        json={
            "full_name": "Jane Doe",
            "phone_number": "9999999999",
            "line1": "123 MG Road",
            "city": "Bengaluru",
            "state": "Karnataka",
            "postal_code": "560001",
        },
        headers=customer_headers,
    ).json()


# --- Addresses ---
def test_address_isolated_between_users(client):
    alice = _make_customer(client, "alice@example.com")
    bob = _make_customer(client, "bob@example.com")

    address = _make_address(client, alice)

    bob_list = client.get("/api/v1/addresses", headers=bob).json()
    assert bob_list == []

    bob_delete = client.delete(f"/api/v1/addresses/{address['id']}", headers=bob)
    assert bob_delete.status_code == 404


# --- Cart ---
def test_add_to_cart_and_view(client):
    admin = _make_admin(client)
    customer = _make_customer(client)
    product = _make_product(client, admin, stock=5)
    variant_id = product["variants"][0]["id"]

    resp = client.post("/api/v1/cart/items", json={"variant_id": variant_id, "quantity": 2}, headers=customer)
    assert resp.status_code == 201
    body = resp.json()
    assert body["items"][0]["quantity"] == 2
    assert float(body["subtotal"]) == 2000.0


def test_cannot_add_more_than_stock(client):
    admin = _make_admin(client)
    customer = _make_customer(client)
    product = _make_product(client, admin, stock=2)
    variant_id = product["variants"][0]["id"]

    resp = client.post("/api/v1/cart/items", json={"variant_id": variant_id, "quantity": 5}, headers=customer)
    assert resp.status_code == 409


def test_remove_cart_item(client):
    admin = _make_admin(client)
    customer = _make_customer(client)
    product = _make_product(client, admin, stock=5)
    variant_id = product["variants"][0]["id"]

    add_resp = client.post(
        "/api/v1/cart/items", json={"variant_id": variant_id, "quantity": 1}, headers=customer
    ).json()
    item_id = add_resp["items"][0]["id"]

    remove_resp = client.delete(f"/api/v1/cart/items/{item_id}", headers=customer)
    assert remove_resp.status_code == 200
    assert remove_resp.json()["items"] == []


# --- Coupons ---
def test_apply_flat_coupon_and_checkout(client):
    admin = _make_admin(client)
    customer = _make_customer(client)
    product = _make_product(client, admin, stock=10, price="1000.00", gst="0")
    variant_id = product["variants"][0]["id"]
    address = _make_address(client, customer)

    client.post(
        "/api/v1/admin/coupons",
        json={"code": "SAVE100", "discount_type": "flat", "discount_value": "100.00", "min_order_value": "500.00"},
        headers=admin,
    )
    client.post("/api/v1/cart/items", json={"variant_id": variant_id, "quantity": 1}, headers=customer)

    apply_resp = client.post("/api/v1/cart/apply-coupon", json={"code": "save100"}, headers=customer)
    assert apply_resp.status_code == 200
    assert float(apply_resp.json()["discount_amount"]) == 100.0

    checkout_resp = client.post(
        "/api/v1/orders", json={"address_id": address["id"], "shipping_charge": "0"}, headers=customer
    )
    assert checkout_resp.status_code == 201
    order = checkout_resp.json()
    assert order["coupon_code"] == "SAVE100"
    assert float(order["discount_amount"]) == 100.0
    assert float(order["total_amount"]) == 900.0  # 1000 - 100 discount, 0 gst, 0 shipping

    # Cart should be cleared after checkout
    cart_after = client.get("/api/v1/cart", headers=customer).json()
    assert cart_after["items"] == []


def test_coupon_below_minimum_order_rejected(client):
    admin = _make_admin(client)
    customer = _make_customer(client)
    product = _make_product(client, admin, stock=10, price="100.00")
    variant_id = product["variants"][0]["id"]

    client.post(
        "/api/v1/admin/coupons",
        json={"code": "BIGORDER", "discount_type": "flat", "discount_value": "50.00", "min_order_value": "5000.00"},
        headers=admin,
    )
    client.post("/api/v1/cart/items", json={"variant_id": variant_id, "quantity": 1}, headers=customer)

    resp = client.post("/api/v1/cart/apply-coupon", json={"code": "BIGORDER"}, headers=customer)
    assert resp.status_code == 400


# --- Checkout stock behavior ---
def test_checkout_decrements_stock(client):
    admin = _make_admin(client)
    customer = _make_customer(client)
    product = _make_product(client, admin, stock=3, price="500.00", gst="0")
    variant_id = product["variants"][0]["id"]
    address = _make_address(client, customer)

    client.post("/api/v1/cart/items", json={"variant_id": variant_id, "quantity": 2}, headers=customer)
    checkout_resp = client.post(
        "/api/v1/orders", json={"address_id": address["id"], "shipping_charge": "0"}, headers=customer
    )
    assert checkout_resp.status_code == 201

    updated_product = client.get(f"/api/v1/products/{product['slug']}").json()
    assert updated_product["variants"][0]["stock_quantity"] == 1


def test_checkout_requires_own_address(client):
    admin = _make_admin(client)
    alice = _make_customer(client, "alice2@example.com")
    bob = _make_customer(client, "bob2@example.com")
    product = _make_product(client, admin, stock=5)
    variant_id = product["variants"][0]["id"]
    bob_address = _make_address(client, bob)

    client.post("/api/v1/cart/items", json={"variant_id": variant_id, "quantity": 1}, headers=alice)
    resp = client.post(
        "/api/v1/orders", json={"address_id": bob_address["id"], "shipping_charge": "0"}, headers=alice
    )
    assert resp.status_code == 404


def test_checkout_empty_cart_rejected(client):
    customer = _make_customer(client, "emptycart@example.com")
    address = _make_address(client, customer)
    resp = client.post(
        "/api/v1/orders", json={"address_id": address["id"], "shipping_charge": "0"}, headers=customer
    )
    assert resp.status_code == 400


# --- Order status lifecycle ---
def test_order_status_transitions_are_validated(client):
    admin = _make_admin(client)
    customer = _make_customer(client, "statusflow@example.com")
    product = _make_product(client, admin, stock=5, price="200.00", gst="0")
    variant_id = product["variants"][0]["id"]
    address = _make_address(client, customer)

    client.post("/api/v1/cart/items", json={"variant_id": variant_id, "quantity": 1}, headers=customer)
    order = client.post(
        "/api/v1/orders", json={"address_id": address["id"], "shipping_charge": "0"}, headers=customer
    ).json()

    # Can't skip straight to delivered from pending
    invalid = client.put(
        f"/api/v1/admin/orders/{order['id']}/status", json={"status": "delivered"}, headers=admin
    )
    assert invalid.status_code == 400

    # Valid forward transition
    valid = client.put(
        f"/api/v1/admin/orders/{order['id']}/status", json={"status": "packed"}, headers=admin
    )
    assert valid.status_code == 200
    assert valid.json()["status"] == "packed"


def test_customer_cannot_view_admin_order_endpoints(client):
    customer = _make_customer(client, "notadmin@example.com")
    resp = client.get("/api/v1/admin/orders", headers=customer)
    assert resp.status_code == 403
