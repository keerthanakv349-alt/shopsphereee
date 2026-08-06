"""
Test fixtures.

WHY SQLITE FOR TESTS INSTEAD OF POSTGRES:
Tests should be fast and not depend on a running Postgres instance. We
swap in an in-memory SQLite DB just for the test session via dependency
override — the app code itself never knows the difference, since it only
talks to `Session` objects. This is a standard pattern; just be aware
SQLite doesn't support every Postgres feature (e.g. our UUID/ENUM columns
are Postgres-specific dialect types, so true integration tests should
also run against a real Postgres in CI — see README "Testing" section).
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.deps import get_razorpay_gateway
from app.core.rate_limit import limiter
from app.db.base import Base
from app.db.session import get_db
from app.main import app

SQLALCHEMY_TEST_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_TEST_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class FakeRazorpayGateway:
    """Deterministic stand-in for LiveRazorpayGateway — see
    app/core/razorpay_gateway.py's module docstring for why the test
    suite never calls the real Razorpay API. Returns fake-but-realistic
    IDs so downstream code that stores/parses them works unchanged."""

    def create_order(self, amount_paise: int, currency: str, receipt: str) -> dict:
        return {
            "id": f"order_fake{uuid.uuid4().hex[:14]}",
            "amount": amount_paise,
            "currency": currency,
            "receipt": receipt,
            "status": "created",
        }

    def create_refund(self, razorpay_payment_id: str, amount_paise: int) -> dict:
        return {"id": f"rfnd_fake{uuid.uuid4().hex[:14]}", "amount": amount_paise, "status": "processed"}


@pytest.fixture()
def client():
    Base.metadata.create_all(bind=engine)
    # Rate limit counters (see app/core/rate_limit.py) live in a
    # module-level in-memory store shared by the whole test process —
    # without resetting it, tests would fail from EACH OTHER'S traffic
    # (e.g. test #40 calling /auth/login gets 429'd because tests #1-39
    # already used up the limit), not from anything the test itself did.
    limiter.reset()

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_razorpay_gateway] = lambda: FakeRazorpayGateway()
    with TestClient(app) as c:
        yield c

    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.clear()
