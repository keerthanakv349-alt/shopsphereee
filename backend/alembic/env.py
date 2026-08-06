"""
Alembic environment script.

WHY THIS MATTERS:
Alembic normally needs its DB URL hardcoded in alembic.ini. Instead, we
pull it from our app's own Settings object (same .env the app uses) so
there's exactly ONE source of truth for the database connection string —
never two configs that can drift out of sync.

We also import Base and every model module here so `--autogenerate`
can diff the live DB schema against our SQLAlchemy models and write the
migration script for us (still reviewed by a human before applying).
"""
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import settings
from app.db.base import Base

# Import every model so Base.metadata knows about all tables.
from app.models.user import User  # noqa: F401
from app.models.address import Address  # noqa: F401
from app.models.catalog import Category, Brand, Product, ProductVariant, ProductImage  # noqa: F401
from app.models.cart import Cart, CartItem  # noqa: F401
from app.models.coupon import Coupon  # noqa: F401
from app.models.order import Order, OrderItem  # noqa: F401
from app.models.payment import Payment  # noqa: F401
from app.models.review import Review  # noqa: F401
from app.models.notification import Notification  # noqa: F401
from app.models.delivery import DeliveryPartner, TrackingEvent  # noqa: F401
from app.models.search_log import SearchQuery  # noqa: F401

config = context.config
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
