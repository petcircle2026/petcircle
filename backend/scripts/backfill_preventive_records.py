"""
Backfill preventive records for existing pets.

After adding new items to preventive_master (e.g., Chronic Care, Bath & Grooming,
Nail Trimming, Ear Cleaning, Food Ordering, Nutrition Planning, Supplements),
existing pets won't have records for those items yet.

This script creates missing preventive records for all active pets.
Safe to re-run — skips items that already have a record for the pet.

Usage:
    cd backend
    python scripts/backfill_preventive_records.py
"""

import sys
import os

# Ensure app package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.pet import Pet
from app.models.preventive_master import PreventiveMaster
from app.models.preventive_record import PreventiveRecord


def main():
    """Create missing preventive records for all active pets."""
    db = SessionLocal()
    try:
        pets = db.query(Pet).filter(Pet.is_deleted == False).all()
        total_created = 0

        for pet in pets:
            # Get all master items applicable to this pet's species.
            masters = (
                db.query(PreventiveMaster)
                .filter(PreventiveMaster.species.in_([pet.species, "both"]))
                .all()
            )

            for master in masters:
                # Check if record already exists.
                existing = (
                    db.query(PreventiveRecord.id)
                    .filter(
                        PreventiveRecord.pet_id == pet.id,
                        PreventiveRecord.preventive_master_id == master.id,
                    )
                    .first()
                )
                if existing:
                    continue

                record = PreventiveRecord(
                    pet_id=pet.id,
                    preventive_master_id=master.id,
                    status="upcoming",
                )
                db.add(record)
                total_created += 1
                print(f"  Created: {pet.name} ({pet.species}) → {master.item_name}")

        db.commit()
        print(f"\nDone. Created {total_created} new preventive record(s).")

    except Exception as e:
        db.rollback()
        print(f"\nError: {e}")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
