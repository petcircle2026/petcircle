"""
PetCircle Phase 1 — Database Connection

Establishes SQLAlchemy engine and session factory using DATABASE_URL
from environment configuration. All database access flows through
the get_db() dependency to ensure proper session lifecycle management.

Connection strategy:
    - Supabase uses PgBouncer (port 6543) in transaction mode.
    - PgBouncer drops connections after each transaction completes.
    - Using NullPool so SQLAlchemy doesn't cache connections that
      PgBouncer has already closed — prevents SSL drop errors.
    - Each request gets a fresh connection, PgBouncer handles pooling.

No business logic lives here — only connection infrastructure.
"""

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from sqlalchemy.pool import NullPool
from typing import Generator
from app.config import settings


# Build connection args for SSL compatibility with Supabase.
connect_args = {}
if "supabase" in settings.DATABASE_URL:
    # Supabase requires SSL but psycopg2 needs keepalive settings
    # to prevent idle connection drops from PgBouncer.
    connect_args = {
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 5,
    }

# SQLAlchemy engine — NullPool because Supabase PgBouncer handles pooling.
# With NullPool, each session creates a fresh connection and closes it
# when done. No stale connections can accumulate and cause SSL errors.
engine = create_engine(
    settings.DATABASE_URL,
    poolclass=NullPool,
    connect_args=connect_args,
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
