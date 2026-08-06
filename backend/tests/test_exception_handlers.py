from sqlalchemy.exc import IntegrityError

from app.core.exception_handlers import register_exception_handlers
from app.models.user import UserRole


def test_duplicate_coupon_via_endpoint_returns_409(client):
    """The endpoint's own pre-check (app/api/v1/admin_coupons.py) should
    catch a plain duplicate and return a clean 409 itself. Confirms that
    path still works after the session.rollback()-on-exception change in
    db/session.py, and that the response never contains raw SQL/psycopg2
    text either way."""
    signup = client.post(
        "/api/v1/auth/signup",
        json={"full_name": "Race Admin", "email": "raceadmin@example.com", "password": "Passw0rd!"},
    )
    from tests.conftest import TestingSessionLocal
    from app.models.user import User

    session = TestingSessionLocal()
    user = session.get(User, signup.json()["user"]["id"])
    user.role = UserRole.ADMIN
    session.commit()
    session.close()
    admin_headers = {"Authorization": f"Bearer {signup.json()['tokens']['access_token']}"}

    first = client.post(
        "/api/v1/admin/coupons",
        json={"code": "RACECOND10", "discount_type": "flat", "discount_value": "10.00"},
        headers=admin_headers,
    )
    second = client.post(
        "/api/v1/admin/coupons",
        json={"code": "RACECOND10", "discount_type": "flat", "discount_value": "5.00"},
        headers=admin_headers,
    )
    assert first.status_code == 201
    assert second.status_code == 409
    assert "INSERT INTO" not in second.json()["detail"]
    assert "psycopg2" not in second.json()["detail"]

    # And the session survives the failed commit cleanly (the
    # db.rollback()-on-exception fix in db/session.py) — a follow-up
    # request in the same test process should work normally, not inherit
    # a broken transaction from the failed insert above.
    followup = client.get("/api/v1/admin/coupons", headers=admin_headers)
    assert followup.status_code == 200


def test_integrity_error_handler_directly_hides_sql_details():
    """Unit-tests the handler function itself with a constructed
    IntegrityError carrying a realistic psycopg2-style message, to prove
    the response body never contains that raw text — independent of
    which endpoint or race condition might trigger it in practice (this
    is what actually catches a race condition that slips past an
    endpoint's own application-level pre-check, unlike the test above)."""
    import asyncio
    from fastapi import FastAPI

    app = FastAPI()
    register_exception_handlers(app)

    handler = app.exception_handlers[IntegrityError]

    fake_orig = Exception(
        'duplicate key value violates unique constraint "uq_review_product_user"\n'
        "DETAIL:  Key (product_id, user_id)=(...) already exists."
    )
    exc = IntegrityError("INSERT INTO reviews (...) VALUES (...)", {"product_id": "..."}, fake_orig)

    response = asyncio.run(handler(None, exc))
    body = response.body.decode()

    assert response.status_code == 409
    assert "INSERT INTO" not in body
    assert "psycopg2" not in body
    assert "uq_review_product_user" not in body
    assert "conflicts with existing data" in body
