"""
One-time script to fix duplicate users in the database.

Finds users with the same mobile_hash, keeps the one with onboarding
progress (or the oldest), and reassigns pets/data from duplicates
to the kept user before soft-deleting the duplicates.

Also adds a UNIQUE constraint on mobile_hash if missing.

Usage:
    cd backend
    set APP_ENV=production
    python -m scripts.fix_duplicate_users
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("APP_ENV", "production")

from sqlalchemy import text
from app.database import SessionLocal


def fix_duplicates():
    db = SessionLocal()
    try:
        # Find duplicate mobile_hash values.
        dupes = db.execute(text("""
            SELECT mobile_hash, COUNT(*) as cnt
            FROM users
            WHERE is_deleted = false
            GROUP BY mobile_hash
            HAVING COUNT(*) > 1
        """)).fetchall()

        if not dupes:
            print("No duplicate users found.")
        else:
            print(f"Found {len(dupes)} mobile numbers with duplicate users.\n")

        for mobile_hash, count in dupes:
            # Get all users with this hash, ordered by progress.
            users = db.execute(text("""
                SELECT id, full_name, onboarding_state, consent_given, created_at
                FROM users
                WHERE mobile_hash = :hash AND is_deleted = false
                ORDER BY
                    CASE onboarding_state
                        WHEN 'complete' THEN 0
                        WHEN 'awaiting_neutered' THEN 1
                        WHEN 'awaiting_weight' THEN 2
                        WHEN 'awaiting_dob' THEN 3
                        WHEN 'awaiting_gender' THEN 4
                        WHEN 'awaiting_breed' THEN 5
                        WHEN 'awaiting_species' THEN 6
                        WHEN 'awaiting_pet_name' THEN 7
                        WHEN 'awaiting_pincode' THEN 8
                        WHEN 'awaiting_name' THEN 9
                        WHEN 'awaiting_consent' THEN 10
                        ELSE 11
                    END,
                    created_at ASC
            """), {"hash": mobile_hash}).fetchall()

            keep = users[0]
            remove = users[1:]

            print(f"Hash: {mobile_hash[:16]}...")
            print(f"  KEEP:   id={keep[0]}, name={keep[1]}, state={keep[2]}, created={keep[4]}")

            for u in remove:
                print(f"  DELETE: id={u[0]}, name={u[1]}, state={u[2]}, created={u[4]}")

                # Reassign pets from duplicate to kept user.
                reassigned = db.execute(text("""
                    UPDATE pets SET user_id = :keep_id
                    WHERE user_id = :remove_id AND is_deleted = false
                """), {"keep_id": keep[0], "remove_id": u[0]})
                if reassigned.rowcount > 0:
                    print(f"    Reassigned {reassigned.rowcount} pet(s)")

                # Soft-delete the duplicate user.
                db.execute(text("""
                    UPDATE users SET is_deleted = true
                    WHERE id = :id
                """), {"id": u[0]})
                print(f"    Soft-deleted")

            print()

        db.commit()
        print("Duplicate cleanup complete.\n")

        # --- Add UNIQUE constraint if missing ---
        print("Checking for UNIQUE constraint on users.mobile_hash...")
        constraints = db.execute(text("""
            SELECT constraint_name
            FROM information_schema.table_constraints
            WHERE table_name = 'users'
              AND constraint_type = 'UNIQUE'
              AND constraint_name LIKE '%mobile_hash%'
        """)).fetchall()

        if constraints:
            print(f"  UNIQUE constraint already exists: {constraints[0][0]}")
        else:
            print("  Adding UNIQUE constraint on mobile_hash...")
            try:
                db.execute(text("""
                    ALTER TABLE users
                    ADD CONSTRAINT uq_users_mobile_hash UNIQUE (mobile_hash)
                """))
                db.commit()
                print("  UNIQUE constraint added successfully.")
            except Exception as e:
                db.rollback()
                print(f"  Failed to add constraint: {e}")
                print("  Fix remaining duplicates first, then re-run.")

    except Exception as e:
        db.rollback()
        print(f"ERROR: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    fix_duplicates()
