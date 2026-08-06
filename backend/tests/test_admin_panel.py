from app.models.user import UserRole
from tests.conftest import TestingSessionLocal


def _make_admin(client, email="admin@example.com", role=UserRole.ADMIN):
    signup = client.post(
        "/api/v1/auth/signup",
        json={"full_name": "Admin User", "email": email, "password": "Passw0rd!"},
    )
    access_token = signup.json()["tokens"]["access_token"]
    user_id = signup.json()["user"]["id"]

    from app.models.user import User

    session = TestingSessionLocal()
    user = session.get(User, user_id)
    user.role = role
    session.commit()
    session.close()

    return {"Authorization": f"Bearer {access_token}"}, user_id


def _make_customer(client, email="customer@example.com"):
    signup = client.post(
        "/api/v1/auth/signup",
        json={"full_name": "Customer One", "email": email, "password": "Passw0rd!"},
    )
    return {"Authorization": f"Bearer {signup.json()['tokens']['access_token']}"}, signup.json()["user"]["id"]


# --- User listing ---
def test_admin_can_list_users(client):
    admin_headers, _ = _make_admin(client)
    _make_customer(client, "someone@example.com")

    resp = client.get("/api/v1/admin/users", headers=admin_headers)
    assert resp.status_code == 200
    emails = [u["email"] for u in resp.json()]
    assert "someone@example.com" in emails
    assert "admin@example.com" in emails


def test_customer_cannot_list_users(client):
    customer_headers, _ = _make_customer(client)
    resp = client.get("/api/v1/admin/users", headers=customer_headers)
    assert resp.status_code == 403


def test_user_search_by_name_or_email(client):
    admin_headers, _ = _make_admin(client)
    _make_customer(client, "findme@example.com")
    _make_customer(client, "other@example.com")

    resp = client.get("/api/v1/admin/users", params={"q": "findme"}, headers=admin_headers)
    results = resp.json()
    assert len(results) == 1
    assert results[0]["email"] == "findme@example.com"


# --- Status toggling ---
def test_admin_can_deactivate_another_user(client):
    admin_headers, _ = _make_admin(client)
    _, customer_id = _make_customer(client)

    resp = client.put(
        f"/api/v1/admin/users/{customer_id}/status", json={"is_active": False}, headers=admin_headers
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False


def test_admin_cannot_deactivate_self(client):
    admin_headers, admin_id = _make_admin(client)
    resp = client.put(
        f"/api/v1/admin/users/{admin_id}/status", json={"is_active": False}, headers=admin_headers
    )
    assert resp.status_code == 400


def test_deactivated_user_cannot_authenticate(client):
    admin_headers, _ = _make_admin(client)
    customer_headers, customer_id = _make_customer(client, "getsbanned@example.com")

    client.put(f"/api/v1/admin/users/{customer_id}/status", json={"is_active": False}, headers=admin_headers)

    resp = client.get("/api/v1/auth/me", headers=customer_headers)
    assert resp.status_code == 401


# --- Role changes (super admin only) ---
def test_regular_admin_cannot_change_roles(client):
    admin_headers, _ = _make_admin(client, role=UserRole.ADMIN)
    _, customer_id = _make_customer(client)

    resp = client.put(
        f"/api/v1/admin/users/{customer_id}/role", json={"role": "admin"}, headers=admin_headers
    )
    assert resp.status_code == 403


def test_super_admin_can_promote_user(client):
    super_admin_headers, _ = _make_admin(client, role=UserRole.SUPER_ADMIN)
    _, customer_id = _make_customer(client)

    resp = client.put(
        f"/api/v1/admin/users/{customer_id}/role", json={"role": "admin"}, headers=super_admin_headers
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "admin"


def test_super_admin_cannot_change_own_role(client):
    super_admin_headers, super_admin_id = _make_admin(client, role=UserRole.SUPER_ADMIN)
    resp = client.put(
        f"/api/v1/admin/users/{super_admin_id}/role", json={"role": "customer"}, headers=super_admin_headers
    )
    assert resp.status_code == 400


# --- Dashboard ---
def test_dashboard_summary_reflects_real_data(client):
    admin_headers, _ = _make_admin(client)
    customer_headers, _ = _make_customer(client)

    category = client.post(
        "/api/v1/admin/categories", json={"name": "Dashboard Cat"}, headers=admin_headers
    ).json()
    brand = client.post("/api/v1/admin/brands", json={"name": "Dashboard Brand"}, headers=admin_headers).json()
    product = client.post(
        "/api/v1/admin/products",
        json={
            "name": "Dashboard Product",
            "category_id": category["id"],
            "brand_id": brand["id"],
            "base_price": "500.00",
            "status": "active",
            "variants": [{"sku": "DASH-1", "stock_quantity": 3}],  # below low-stock threshold of 5
        },
        headers=admin_headers,
    ).json()
    address = client.post(
        "/api/v1/addresses",
        json={
            "full_name": "Jane",
            "phone_number": "9999999999",
            "line1": "1 Road",
            "city": "City",
            "state": "State",
            "postal_code": "111111",
        },
        headers=customer_headers,
    ).json()
    client.post(
        "/api/v1/cart/items",
        json={"variant_id": product["variants"][0]["id"], "quantity": 1},
        headers=customer_headers,
    )
    client.post(
        "/api/v1/orders", json={"address_id": address["id"], "shipping_charge": "0"}, headers=customer_headers
    )

    resp = client.get("/api/v1/admin/dashboard/summary", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_orders"] >= 1
    assert body["total_customers"] >= 1
    assert body["total_products"] >= 1
    assert body["low_stock_variant_count"] >= 1
    assert len(body["recent_orders"]) >= 1
    # No payment was made yet, so revenue should not count this unpaid order.
    assert float(body["total_revenue"]) == 0.0


def test_customer_cannot_view_dashboard(client):
    customer_headers, _ = _make_customer(client)
    resp = client.get("/api/v1/admin/dashboard/summary", headers=customer_headers)
    assert resp.status_code == 403
