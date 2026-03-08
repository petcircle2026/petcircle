"""
Clear all data from the database (keeps preventive_master reference data).

Truncates tables in FK-safe order (children first) using CASCADE.
Preserves the preventive_master table since it contains static
reference data seeded by seed_preventive_master.py.

Usage:
    cd backend
    python scripts/clear_database.py
"""

import sys
import os

# Ensure app package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from sqlalchemy import text


# Tables to truncate in FK-safe order (children before parents).
# preventive_master is excluded — it holds static reference data.
TABLES_TO_CLEAR = [
    "message_logs",
    "conflict_flags",
    "reminders",
    "preventive_records",
    "documents",
    "dashboard_tokens",
    "pets",
    "users",
]


def main():
    """Truncate all data tables, preserving preventive_master."""
    db = SessionLocal()
    try:
        for table in TABLES_TO_CLEAR:
            db.execute(text(f"TRUNCATE TABLE {table} CASCADE"))
            print(f"  Truncated {table}")
        db.commit()
        print("\nAll tables cleared successfully.")
    except Exception as e:
        db.rollback()
        print(f"\nError: {e}")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
