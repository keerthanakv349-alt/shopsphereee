"""
Cross-database UUID column type, and a helper for Postgres-backed enum
columns.

WHY THIS EXISTS:
Postgres has a native UUID type (fast, indexed properly). SQLite doesn't.
Our production DB is Postgres, but tests run against in-memory SQLite for
speed (see tests/conftest.py). This TypeDecorator stores a real UUID
column on Postgres and transparently falls back to a CHAR(36) string on
any other backend, so the same model code works in both without an
if/else scattered through every model file.
"""
import enum
import uuid
from typing import Type

from sqlalchemy import CHAR, Enum, TypeDecorator
from sqlalchemy.dialects.postgresql import UUID as PG_UUID


class GUID(TypeDecorator):
    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return str(value)
        if not isinstance(value, uuid.UUID):
            return str(uuid.UUID(value))
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(value)


def pg_enum(enum_class: Type[enum.Enum], name: str, **kwargs) -> Enum:
    """
    Wraps SQLAlchemy's Enum() with the one option every enum column in
    this project needs and is easy to forget: values_callable.

    THE BUG THIS PREVENTS (confirmed against a real bug in this codebase):
    Given `class UserRole(str, enum.Enum): CUSTOMER = "customer"`, calling
    plain `Enum(UserRole, name="user_role")` makes SQLAlchemy bind the
    member's NAME ("CUSTOMER") to the database on every INSERT/UPDATE/WHERE
    — not its VALUE ("customer") — even though UserRole is a `str` subclass
    and `UserRole.CUSTOMER == "customer"` is True in plain Python. This is
    a well-documented SQLAlchemy default (see the "Enum" section of the
    SQLAlchemy docs) that is very easy to miss because nothing about the
    model code looks wrong, and — critically — SQLite doesn't catch it:
    SQLite emulates an enum with a VARCHAR + CHECK(value IN (...))
    constraint built from the SAME (wrong) name-based list SQLAlchemy is
    already writing, so it's self-consistently wrong and every test passes.
    Real Postgres has a native ENUM type with its own fixed label set —
    this project's Alembic migrations define those labels as the lowercase
    VALUE strings (e.g. "customer", "admin"), so the mismatch surfaces
    immediately as `psycopg2.errors.InvalidTextRepresentation: invalid
    input value for enum user_role: "CUSTOMER"` — on literally the first
    write to that column, i.e. signup.

    `values_callable=lambda obj: [e.value for e in obj]` tells SQLAlchemy
    to use `.value` instead of `.name` — matching what every migration in
    this project actually created. Using this helper for every enum column
    (instead of calling Enum() directly) means this mistake can't happen
    again on the next enum without someone deliberately bypassing it.
    """
    return Enum(enum_class, name=name, values_callable=lambda obj: [e.value for e in obj], **kwargs)
