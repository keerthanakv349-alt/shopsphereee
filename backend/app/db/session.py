"""
Database engine and session factory.

WHY A SESSION FACTORY + DEPENDENCY:
SQLAlchemy Sessions are NOT thread-safe and shouldn't be shared across
requests. Instead, we create a fresh Session per incoming HTTP request,
use it, then close it — this is the "unit of work" pattern. FastAPI's
dependency injection (see get_db below, used as `db: Session = Depends(get_db)`
in route handlers) makes this automatic: FastAPI calls get_db(), yields a
session to the route, and guarantees cleanup (session.close()) runs even
if the route raises an exception.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception:
        # Roll back explicitly on any exception (including one raised
        # inside the route AFTER using this session) before closing.
        # Without this, a session left mid-transaction after a failed
        # commit (e.g. a unique-constraint violation) depends on
        # SessionLocal.close()'s implicit cleanup to discard it — that
        # happens to work today, but relying on it is fragile and
        # non-obvious. An explicit rollback here makes "this session is
        # never returned to the pool in a half-finished state" a
        # guarantee, not an implementation detail of close().
        db.rollback()
        raise
    finally:
        db.close()
