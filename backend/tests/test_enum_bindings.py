"""
Enum column binding regression test.

WHY THIS TEST EXISTS:
This project had a real bug: every SQLAlchemy `Enum(SomeEnum, name=...)`
column defaulted to binding the Python enum member's `.name` (e.g.
"CUSTOMER") to the database, not its `.value` ("customer") — even though
every enum here is a `str` subclass. Every Alembic migration in this
project defines its Postgres enum labels using `.value` strings
(lowercase), so the mismatch caused
`psycopg2.errors.InvalidTextRepresentation` on literally every write to
an enum column, starting with signup.

The rest of the test suite runs against SQLite (see conftest.py, for
speed) and NEVER caught this: SQLite emulates an enum with a
`VARCHAR + CHECK(value IN (...))` constraint built from the exact same
(wrong) name-based list SQLAlchemy was already binding — so it was
self-consistently wrong, and every SQLite-backed test passed regardless.
Only a real Postgres enum type (with its own fixed, migration-defined
label set) exposes the mismatch.

This test doesn't need a real Postgres connection to catch the class of
bug, though — it only needs to inspect what SQLAlchemy WOULD send to
Postgres (via the dialect's bind_processor) and compare that against
each enum's `.value`, which is what every migration in this project
uses for its labels. Any future enum column that forgets to use
`app.db.types.pg_enum` (which sets `values_callable` correctly) will
fail this test immediately, without needing a live Postgres instance in
CI.
"""
from sqlalchemy.dialects import postgresql

from app.models.catalog import Product, ProductStatus
from app.models.coupon import Coupon, DiscountType
from app.models.delivery import TrackingEvent, TrackingStatus
from app.models.notification import Notification, NotificationType
from app.models.order import Order, OrderStatus
from app.models.payment import Payment, PaymentStatus
from app.models.user import User, UserRole

# (table.column, enum class) for every enum column in the project.
# Add new enum columns here as they're introduced.
ENUM_COLUMNS = [
    (User.__table__.c.role, UserRole),
    (Product.__table__.c.status, ProductStatus),
    (Order.__table__.c.status, OrderStatus),
    (Payment.__table__.c.status, PaymentStatus),
    (Coupon.__table__.c.discount_type, DiscountType),
    (Notification.__table__.c.notification_type, NotificationType),
    (TrackingEvent.__table__.c.status, TrackingStatus),
]


def test_every_enum_column_binds_dot_value_not_dot_name():
    dialect = postgresql.dialect()

    for column, enum_cls in ENUM_COLUMNS:
        bind_processor = column.type.bind_processor(dialect)
        for member in enum_cls:
            sent_to_db = bind_processor(member)
            assert sent_to_db == member.value, (
                f"{column.table.name}.{column.name}: binding {enum_cls.__name__}.{member.name} "
                f"sends {sent_to_db!r} to Postgres, but should send {member.value!r} "
                f"(its .value). This means the column was defined with a bare Enum(...) "
                f"instead of app.db.types.pg_enum(...) — use pg_enum() instead."
            )


def test_every_enum_columns_valid_label_set_uses_values_not_names():
    """A second angle on the same property: the column's declared list of
    valid Postgres labels (`.enums`) should be the enum's VALUES, not its
    member NAMES — these differ for every enum in this project (member
    names are UPPER_SNAKE_CASE, values are lower_snake_case)."""
    for column, enum_cls in ENUM_COLUMNS:
        expected = [member.value for member in enum_cls]
        assert column.type.enums == expected, (
            f"{column.table.name}.{column.name}: column.type.enums={column.type.enums!r}, "
            f"expected {expected!r}"
        )
