"""
Shared declarative base class every ORM model inherits from.

WHY A SEPARATE FILE:
Alembic (migrations tool) needs to import ALL models so it can compare
them against the live database schema and auto-generate migration scripts.
Keeping `Base` here (instead of defining it inside models/user.py) avoids
circular imports: models import Base from here, and alembic/env.py imports
Base from here too, without needing to import individual model files
directly in two different places.
"""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
