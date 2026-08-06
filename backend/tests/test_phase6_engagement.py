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

    return {"Authorization": f"Bearer {access_token}"}, access_token


def _make_customer(client, email="customer@example.com"):
    signup = client.post(
        "/api/v1/auth/signup",
        json={"full_name": "Customer One", "email": email, "password": "Passw0rd!"},
    )
    token = signup.json()["tokens"]["access_token"]
    return {"Authorization": f"Bearer {token}"}, token, signup.json()["user"]["id"]


def _make_product(client, admin_headers, name="Test Product", price="500.00"):
    category = client.post("/api/v1/admin/categories", json={"name": f"Cat-{name}"}, headers=admin_headers).json()
    brand = client.post("/api/v1/admin/brands", json={"name": f"Brand-{name}"}, headers=admin_headers).json()
    product = client.post(
        "/api/v1/admin/products",
        json={
            "name": name,
            "category_id": category["id"],
            "brand_id": brand["id"],
            "base_price": price,
            "gst_percentage": "0",
            "status": "active",
            "variants": [{"sku": f"SKU-{name}", "stock_quantity": 10}],
        },
        headers=admin_headers,
    ).json()
    return product, category, brand


def _place_order(client, admin_headers, customer_headers, product):
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
        "/api/v1/cart/items", json={"variant_id": product["variants"][0]["id"], "quantity": 1}, headers=customer_headers
    )
    return client.post(
        "/api/v1/orders", json={"address_id": address["id"], "shipping_charge": "0"}, headers=customer_headers
    ).json()


# --- Reviews ---
def test_verified_purchase_detected_correctly(client):
    admin_headers, _ = _make_admin(client)
    customer_headers, _, _ = _make_customer(client)
    product, _, _ = _make_product(client, admin_headers, "ReviewedProduct")
    _place_order(client, admin_headers, customer_headers, product)

    resp = client.post(
        f"/api/v1/products/{product['id']}/reviews",
        json={"rating": 5, "comment": "Great product, exactly as described!"},
        headers=customer_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["is_verified_purchase"] is True


def test_unverified_review_when_never_purchased(client):
    admin_headers, _ = _make_admin(client)
    customer_headers, _, _ = _make_customer(client, "neverbought@example.com")
    product, _, _ = _make_product(client, admin_headers, "NeverBoughtProduct")

    resp = client.post(
        f"/api/v1/products/{product['id']}/reviews",
        json={"rating": 3, "comment": "Looks fine from the pictures I guess."},
        headers=customer_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["is_verified_purchase"] is False


def test_cannot_review_same_product_twice(client):
    admin_headers, _ = _make_admin(client)
    customer_headers, _, _ = _make_customer(client, "double@example.com")
    product, _, _ = _make_product(client, admin_headers, "DoubleReviewProduct")

    payload = {"rating": 4, "comment": "Solid, would recommend to a friend."}
    first = client.post(f"/api/v1/products/{product['id']}/reviews", json=payload, headers=customer_headers)
    second = client.post(f"/api/v1/products/{product['id']}/reviews", json=payload, headers=customer_headers)
    assert first.status_code == 201
    assert second.status_code == 409


def test_review_summary_computes_average(client):
    admin_headers, _ = _make_admin(client)
    product, _, _ = _make_product(client, admin_headers, "AvgRatingProduct")

    ratings = [5, 3, 4]
    for i, rating in enumerate(ratings):
        headers, _, _ = _make_customer(client, f"rater{i}@example.com")
        client.post(
            f"/api/v1/products/{product['id']}/reviews",
            json={"rating": rating, "comment": "A reasonably detailed opinion about this item."},
            headers=headers,
        )

    resp = client.get(f"/api/v1/products/{product['id']}/reviews")
    body = resp.json()
    assert body["review_count"] == 3
    assert body["average_rating"] == 4.0
    assert body["reviews"][0]["reviewer_name"]  # joined correctly, not empty


def test_helpful_vote_increments(client):
    admin_headers, _ = _make_admin(client)
    customer_headers, _, _ = _make_customer(client, "helpful@example.com")
    product, _, _ = _make_product(client, admin_headers, "HelpfulProduct")

    review = client.post(
        f"/api/v1/products/{product['id']}/reviews",
        json={"rating": 5, "comment": "Very useful review text goes here."},
        headers=customer_headers,
    ).json()

    resp = client.post(f"/api/v1/reviews/{review['id']}/helpful", headers=customer_headers)
    assert resp.status_code == 200
    assert resp.json()["helpful_count"] == 1


# --- Notifications (persisted + live WebSocket push) ---
def test_order_status_change_creates_notification(client):
    admin_headers, _ = _make_admin(client)
    customer_headers, _, _ = _make_customer(client, "notifyme@example.com")
    product, _, _ = _make_product(client, admin_headers, "NotifyProduct")
    order = _place_order(client, admin_headers, customer_headers, product)

    client.put(f"/api/v1/admin/orders/{order['id']}/status", json={"status": "packed"}, headers=admin_headers)

    notifications = client.get("/api/v1/notifications", headers=customer_headers).json()
    assert any(n["related_order_id"] == order["id"] for n in notifications)


def test_notification_pushed_live_over_websocket(client):
    admin_headers, _ = _make_admin(client)
    customer_headers, customer_token, _ = _make_customer(client, "wsuser@example.com")
    product, _, _ = _make_product(client, admin_headers, "WsProduct")
    order = _place_order(client, admin_headers, customer_headers, product)

    with client.websocket_connect(f"/api/v1/ws/notifications?token={customer_token}") as websocket:
        client.put(f"/api/v1/admin/orders/{order['id']}/status", json={"status": "packed"}, headers=admin_headers)
        message = websocket.receive_json()

    assert message["related_order_id"] == order["id"]
    assert "packed" in message["message"]


def test_websocket_rejects_invalid_token(client):
    from starlette.websockets import WebSocketDisconnect

    try:
        with client.websocket_connect("/api/v1/ws/notifications?token=not-a-real-token"):
            pass
        assert False, "expected the connection to be rejected"
    except WebSocketDisconnect:
        pass


def test_mark_notification_read(client):
    admin_headers, _ = _make_admin(client)
    customer_headers, _, _ = _make_customer(client, "markread@example.com")
    product, _, _ = _make_product(client, admin_headers, "MarkReadProduct")
    order = _place_order(client, admin_headers, customer_headers, product)
    client.put(f"/api/v1/admin/orders/{order['id']}/status", json={"status": "packed"}, headers=admin_headers)

    notifications = client.get("/api/v1/notifications", headers=customer_headers).json()
    notification_id = notifications[0]["id"]

    resp = client.put(f"/api/v1/notifications/{notification_id}/read", headers=customer_headers)
    assert resp.status_code == 200
    assert resp.json()["is_read"] is True


# --- Delivery tracking ---
def test_admin_can_add_tracking_events_and_customer_can_view(client):
    admin_headers, _ = _make_admin(client)
    customer_headers, _, _ = _make_customer(client, "tracking@example.com")
    product, _, _ = _make_product(client, admin_headers, "TrackedProduct")
    order = _place_order(client, admin_headers, customer_headers, product)

    partner = client.post(
        "/api/v1/admin/delivery-partners",
        json={"name": "Ravi Kumar", "phone_number": "9876543210", "vehicle_number": "KA01AB1234"},
        headers=admin_headers,
    ).json()

    event_resp = client.post(
        f"/api/v1/admin/orders/{order['id']}/tracking-events",
        json={
            "status": "shipped",
            "location_label": "Bengaluru Hub",
            "latitude": 12.9716,
            "longitude": 77.5946,
            "delivery_partner_id": partner["id"],
        },
        headers=admin_headers,
    )
    assert event_resp.status_code == 201
    assert event_resp.json()["delivery_partner"]["name"] == "Ravi Kumar"

    tracking = client.get(f"/api/v1/orders/{order['id']}/tracking", headers=customer_headers)
    assert tracking.status_code == 200
    assert len(tracking.json()) == 1
    assert tracking.json()[0]["status"] == "shipped"


def test_customer_cannot_view_others_tracking(client):
    admin_headers, _ = _make_admin(client)
    alice_headers, _, _ = _make_customer(client, "alice3@example.com")
    bob_headers, _, _ = _make_customer(client, "bob3@example.com")
    product, _, _ = _make_product(client, admin_headers, "PrivateTrackProduct")
    order = _place_order(client, admin_headers, alice_headers, product)

    resp = client.get(f"/api/v1/orders/{order['id']}/tracking", headers=bob_headers)
    assert resp.status_code == 404


def test_customer_cannot_add_tracking_events(client):
    admin_headers, _ = _make_admin(client)
    customer_headers, _, _ = _make_customer(client, "notadmin2@example.com")
    product, _, _ = _make_product(client, admin_headers, "NoAccessProduct")
    order = _place_order(client, admin_headers, customer_headers, product)

    resp = client.post(
        f"/api/v1/admin/orders/{order['id']}/tracking-events",
        json={"status": "shipped"},
        headers=customer_headers,
    )
    assert resp.status_code == 403


# --- Search ---
def test_search_log_and_trending(client):
    for _ in range(3):
        client.post("/api/v1/search/log", params={"q": "sneakers"})
    client.post("/api/v1/search/log", params={"q": "boots"})

    trending = client.get("/api/v1/search/trending").json()
    assert trending[0] == "sneakers"  # searched 3x, should rank above boots (1x)


def test_search_suggestions_prefix_match(client):
    admin_headers, _ = _make_admin(client)
    _make_product(client, admin_headers, "Suggestion Sneaker")

    resp = client.get("/api/v1/search/suggestions", params={"q": "Suggestion"})
    assert resp.status_code == 200
    assert any("Suggestion" in name for name in resp.json())


# --- Recommendations ---
def test_related_products_same_category(client):
    admin_headers, _ = _make_admin(client)
    category = client.post("/api/v1/admin/categories", json={"name": "Shared Category"}, headers=admin_headers).json()
    brand = client.post("/api/v1/admin/brands", json={"name": "Shared Brand"}, headers=admin_headers).json()

    def make_in_category(name):
        return client.post(
            "/api/v1/admin/products",
            json={
                "name": name,
                "category_id": category["id"],
                "brand_id": brand["id"],
                "base_price": "100.00",
                "status": "active",
                "variants": [{"sku": f"REL-{name}", "stock_quantity": 5}],
            },
            headers=admin_headers,
        ).json()

    main_product = make_in_category("Main Related Product")
    make_in_category("Sibling Related Product")

    resp = client.get(f"/api/v1/products/{main_product['slug']}/related")
    assert resp.status_code == 200
    names = [p["name"] for p in resp.json()]
    assert "Sibling Related Product" in names
    assert "Main Related Product" not in names


def test_frequently_bought_together(client):
    admin_headers, _ = _make_admin(client)
    customer_headers, _, _ = _make_customer(client, "fbt@example.com")
    category = client.post("/api/v1/admin/categories", json={"name": "FBT Category"}, headers=admin_headers).json()
    brand = client.post("/api/v1/admin/brands", json={"name": "FBT Brand"}, headers=admin_headers).json()

    def make_product(name):
        return client.post(
            "/api/v1/admin/products",
            json={
                "name": name,
                "category_id": category["id"],
                "brand_id": brand["id"],
                "base_price": "200.00",
                "gst_percentage": "0",
                "status": "active",
                "variants": [{"sku": f"FBT-{name}", "stock_quantity": 5}],
            },
            headers=admin_headers,
        ).json()

    product_a = make_product("FBT Product A")
    product_b = make_product("FBT Product B")

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
        "/api/v1/cart/items", json={"variant_id": product_a["variants"][0]["id"], "quantity": 1}, headers=customer_headers
    )
    client.post(
        "/api/v1/cart/items", json={"variant_id": product_b["variants"][0]["id"], "quantity": 1}, headers=customer_headers
    )
    client.post("/api/v1/orders", json={"address_id": address["id"], "shipping_charge": "0"}, headers=customer_headers)

    resp = client.get(f"/api/v1/products/{product_a['slug']}/frequently-bought-together")
    assert resp.status_code == 200
    names = [p["name"] for p in resp.json()]
    assert "FBT Product B" in names
