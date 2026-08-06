import io

from PIL import Image

from app.db.base import Base
from app.models.user import UserRole
from tests.conftest import TestingSessionLocal


def _make_admin(client, email="admin@example.com"):
    """Sign up a normal user via the real API, then promote them to admin
    directly in the DB — there's no public "become an admin" endpoint by
    design, so tests reach into the DB the same way a seed script would."""
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


def _make_category_and_brand(client, admin_headers):
    category = client.post(
        "/api/v1/admin/categories", json={"name": "Footwear"}, headers=admin_headers
    ).json()
    brand = client.post(
        "/api/v1/admin/brands", json={"name": "Nike"}, headers=admin_headers
    ).json()
    return category, brand


def test_customer_cannot_create_product(client):
    signup = client.post(
        "/api/v1/auth/signup",
        json={"full_name": "Regular Customer", "email": "cust@example.com", "password": "Passw0rd!"},
    )
    headers = {"Authorization": f"Bearer {signup.json()['tokens']['access_token']}"}

    resp = client.post(
        "/api/v1/admin/products",
        json={
            "name": "Shoe",
            "category_id": "00000000-0000-0000-0000-000000000000",
            "brand_id": "00000000-0000-0000-0000-000000000000",
            "base_price": "100.00",
            "variants": [{"sku": "SHOE-1", "stock_quantity": 5}],
        },
        headers=headers,
    )
    assert resp.status_code == 403


def test_admin_creates_product_with_variants_in_one_transaction(client):
    admin_headers = _make_admin(client)
    category, brand = _make_category_and_brand(client, admin_headers)

    resp = client.post(
        "/api/v1/admin/products",
        json={
            "name": "Air Max 90",
            "description": "A classic sneaker.",
            "category_id": category["id"],
            "brand_id": brand["id"],
            "base_price": "8999.00",
            "discount_percentage": "10",
            "gst_percentage": "12",
            "status": "active",
            "variants": [
                {"sku": "AM90-BLK-9", "size": "UK9", "color": "Black", "stock_quantity": 10},
                {"sku": "AM90-BLK-10", "size": "UK10", "color": "Black", "stock_quantity": 5},
            ],
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["slug"] == "air-max-90"
    assert len(body["variants"]) == 2
    assert body["category"]["name"] == "Footwear"


def test_duplicate_sku_rejected(client):
    admin_headers = _make_admin(client)
    category, brand = _make_category_and_brand(client, admin_headers)

    payload = {
        "name": "Duplicate SKU Shoe",
        "category_id": category["id"],
        "brand_id": brand["id"],
        "base_price": "1000.00",
        "variants": [{"sku": "DUP-1", "stock_quantity": 1}],
    }
    first = client.post("/api/v1/admin/products", json=payload, headers=admin_headers)
    payload["name"] = "Another Product"
    second = client.post("/api/v1/admin/products", json=payload, headers=admin_headers)

    assert first.status_code == 201
    assert second.status_code == 409


def test_public_listing_excludes_draft_products(client):
    admin_headers = _make_admin(client)
    category, brand = _make_category_and_brand(client, admin_headers)

    client.post(
        "/api/v1/admin/products",
        json={
            "name": "Draft Product",
            "category_id": category["id"],
            "brand_id": brand["id"],
            "base_price": "500.00",
            "status": "draft",
            "variants": [{"sku": "DRAFT-1", "stock_quantity": 1}],
        },
        headers=admin_headers,
    )
    client.post(
        "/api/v1/admin/products",
        json={
            "name": "Live Product",
            "category_id": category["id"],
            "brand_id": brand["id"],
            "base_price": "500.00",
            "status": "active",
            "variants": [{"sku": "LIVE-1", "stock_quantity": 1}],
        },
        headers=admin_headers,
    )

    resp = client.get("/api/v1/products")
    names = [item["name"] for item in resp.json()["items"]]
    assert "Live Product" in names
    assert "Draft Product" not in names


def test_public_filters_search_and_sort(client):
    admin_headers = _make_admin(client)
    category, brand = _make_category_and_brand(client, admin_headers)

    for name, price in [("Red Sneaker", "1000"), ("Blue Sneaker", "2000"), ("Leather Boot", "3000")]:
        client.post(
            "/api/v1/admin/products",
            json={
                "name": name,
                "category_id": category["id"],
                "brand_id": brand["id"],
                "base_price": price,
                "status": "active",
                "variants": [{"sku": f"SKU-{name}", "stock_quantity": 1}],
            },
            headers=admin_headers,
        )

    search_resp = client.get("/api/v1/products", params={"q": "sneaker"})
    assert search_resp.json()["total"] == 2

    price_filtered = client.get("/api/v1/products", params={"min_price": 1500})
    assert price_filtered.json()["total"] == 2

    sorted_desc = client.get("/api/v1/products", params={"sort": "price_desc"})
    prices = [float(item["base_price"]) for item in sorted_desc.json()["items"]]
    assert prices == sorted(prices, reverse=True)


def test_product_detail_by_slug(client):
    admin_headers = _make_admin(client)
    category, brand = _make_category_and_brand(client, admin_headers)

    client.post(
        "/api/v1/admin/products",
        json={
            "name": "Detail Product",
            "category_id": category["id"],
            "brand_id": brand["id"],
            "base_price": "777.00",
            "status": "active",
            "variants": [{"sku": "DETAIL-1", "stock_quantity": 2}],
        },
        headers=admin_headers,
    )

    resp = client.get("/api/v1/products/detail-product")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Detail Product"
    assert resp.json()["variants"][0]["sku"] == "DETAIL-1"

    missing = client.get("/api/v1/products/does-not-exist")
    assert missing.status_code == 404


def test_image_upload_compresses_and_attaches_to_product(client):
    admin_headers = _make_admin(client)
    category, brand = _make_category_and_brand(client, admin_headers)

    product = client.post(
        "/api/v1/admin/products",
        json={
            "name": "Image Test Shoe",
            "category_id": category["id"],
            "brand_id": brand["id"],
            "base_price": "999.00",
            "variants": [{"sku": "IMG-1", "stock_quantity": 1}],
        },
        headers=admin_headers,
    ).json()

    # Build a real in-memory PNG so Pillow has valid bytes to process.
    buffer = io.BytesIO()
    Image.new("RGB", (2000, 2000), color="red").save(buffer, format="PNG")
    buffer.seek(0)

    resp = client.post(
        f"/api/v1/admin/products/{product['id']}/images",
        files={"file": ("test.png", buffer, "image/png")},
        params={"is_primary": True},
        headers=admin_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["image_url"].startswith("/media/products/")
    assert resp.json()["is_primary"] is True


def test_soft_delete_sets_status_inactive_not_row_deletion(client):
    admin_headers = _make_admin(client)
    category, brand = _make_category_and_brand(client, admin_headers)

    product = client.post(
        "/api/v1/admin/products",
        json={
            "name": "Deletable Product",
            "category_id": category["id"],
            "brand_id": brand["id"],
            "base_price": "100.00",
            "status": "active",
            "variants": [{"sku": "DEL-1", "stock_quantity": 1}],
        },
        headers=admin_headers,
    ).json()

    delete_resp = client.delete(f"/api/v1/admin/products/{product['id']}", headers=admin_headers)
    assert delete_resp.status_code == 204

    # Gone from the public catalog...
    assert client.get(f"/api/v1/products/{product['slug']}").status_code == 404

    # ...but still visible (and intact) to admins, just with status inactive.
    admin_listing = client.get("/api/v1/admin/products", headers=admin_headers).json()
    match = next(p for p in admin_listing["items"] if p["id"] == product["id"])
    assert match["status"] == "inactive"
