"""
PetCircle Phase 1 — Database Connection

Establishes SQLAlchemy engine and session factory using DATABASE_URL
from environment configuration. All database access flows through
the get_db() dependency to ensure proper session lifecycle management.

No business logic lives here — only connection infrastructure.
"""

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from sqlalchemy.exc import OperationalError, DBAPIError
from typing import Generator
from app.config import settings


# SQLAlchemy engine — uses DATABASE_URL from validated environment config.
# pool_pre_ping ensures stale connections are detected and recycled.
# pool_recycle aggressively recycles connections to prevent SSL drops
# on Supabase's connection pooler (PgBouncer).
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,
    # Recycle connections every 5 minutes to prevent SSL connection drops.
    # Supabase pooler may close idle connections; this ensures fresh ones.
    pool_recycle=300,
)


# Invalidate connections on checkout if they are in a broken state.
# This prevents "SSL connection has been closed unexpectedly" cascading failures.
@event.listens_for(engine, "checkout")
def _checkout_listener(dbapi_conn, connection_record, connection_proxy):
    """Test connection health on checkout from pool."""
    try:
        cursor = dbapi_conn.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
    except Exception:
        # Connection is dead — raise DisconnectionError to trigger pool recycling.
        raise OperationalError(
            "Connection health check failed", None, None
        )


# Session factory — autocommit and autoflush disabled for explicit transaction control.
# Every DB write must be committed explicitly to prevent silent data loss.
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

# Declarative base for all SQLAlchemy models.
# Every model in app/models/ must inherit from this base.
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that provides a database session.

    Yields a session and ensures it is closed after the request completes,
    regardless of whether the request succeeded or raised an exception.
    Rolls back on errors to prevent dirty session state from poisoning
    subsequent requests.
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
