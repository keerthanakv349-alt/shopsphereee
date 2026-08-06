from app.core.rate_limit import limiter


def test_rate_limit_blocks_after_threshold(client):
    # AUTH_RATE_LIMIT is 5/minute (see app/core/rate_limit.py) — the 6th
    # rapid request in the same window should be rejected with 429.
    for i in range(5):
        resp = client.post(
            "/api/v1/auth/login",
            json={"email": f"nonexistent{i}@example.com", "password": "whatever123"},
        )
        assert resp.status_code == 401  # wrong credentials, but NOT rate-limited yet

    sixth = client.post(
        "/api/v1/auth/login", json={"email": "nonexistent999@example.com", "password": "whatever123"}
    )
    assert sixth.status_code == 429


def test_rate_limit_is_per_key_not_global_across_endpoints(client):
    # Exhausting the login limit shouldn't affect an unrelated,
    # unlimited endpoint like the product catalog.
    for i in range(5):
        client.post("/api/v1/auth/login", json={"email": f"x{i}@example.com", "password": "whatever123"})

    resp = client.get("/api/v1/products")
    assert resp.status_code == 200


def test_security_headers_present_on_every_response(client):
    resp = client.get("/health")
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


def test_security_headers_present_even_on_error_responses(client):
    resp = client.get("/api/v1/products/does-not-exist-slug")
    assert resp.status_code == 404
    assert resp.headers["X-Content-Type-Options"] == "nosniff"


def test_request_id_header_present_and_unique_per_request(client):
    first = client.get("/health")
    second = client.get("/health")
    assert "X-Request-ID" in first.headers
    assert "X-Request-ID" in second.headers
    assert first.headers["X-Request-ID"] != second.headers["X-Request-ID"]


def test_validation_error_envelope_includes_request_id(client):
    resp = client.post(
        "/api/v1/auth/signup",
        json={"full_name": "A", "email": "not-an-email", "password": "short"},
    )
    assert resp.status_code == 422
    body = resp.json()
    assert "request_id" in body
    assert "detail" in body


def test_health_check(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_docs_available_in_development_mode(client):
    # ENVIRONMENT defaults to "development" in .env.example — /docs
    # should be reachable in that mode (see app/main.py's docs_url logic).
    resp = client.get("/docs")
    assert resp.status_code == 200


def teardown_module(module):
    # Leave the shared limiter clean for any test module that runs after
    # this file, regardless of pytest's collection order.
    limiter.reset()
