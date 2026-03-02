"""
Seed the preventive master table.

Usage:
    cd backend
    python scripts/seed_preventive_master.py
"""

import sys
import os

# Ensure app package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.services.preventive_seeder import seed_preventive_master


def main():
    """Seed the preventive master table with default data."""
    db = SessionLocal()
    try:
        seed_preventive_master(db)
        print("Preventive master table seeded successfully.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
