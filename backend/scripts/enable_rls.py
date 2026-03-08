"""
One-time script to enable Row Level Security (RLS) on users, pets, and documents tables.

Creates policies that:
    - Allow the service_role (used by backend) full access (bypasses RLS by default)
    - Deny all access to anon and authenticated roles (no direct client access in Phase 1)

In Supabase, the service_role key bypasses RLS automatically, so enabling RLS
with restrictive policies effectively blocks any non-backend access (e.g.,
direct Supabase client calls with the anon key).

Usage:
    cd backend
    set APP_ENV=production
    python -m scripts.enable_rls
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("APP_ENV", "production")

from sqlalchemy import text
from app.database import SessionLocal


TABLES = ["users", "pets", "documents"]


def enable_rls():
    db = SessionLocal()
    try:
        # --- Step 1: Check current RLS status ---
        print("Current RLS status:")
        for table in TABLES:
            result = db.execute(text(
                "SELECT relrowsecurity FROM pg_class WHERE relname = :table"
            ), {"table": table}).fetchone()
            status = "ENABLED" if result and result[0] else "DISABLED"
            print(f"  {table}: {status}")
        print()

        # --- Step 2: Enable RLS on each table ---
        for table in TABLES:
            print(f"Enabling RLS on '{table}'...")
            db.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;"))
            print(f"  RLS enabled on '{table}'.")

        db.commit()
        print()

        # --- Step 3: Create restrictive policies ---
        # In Supabase, service_role bypasses RLS entirely.
        # We create a deny-all policy for anon/authenticated roles so that
        # nobody can access these tables directly via Supabase client.
        #
        # Policy: allow nothing for non-service roles.
        # Since service_role bypasses RLS, the backend is unaffected.

        for table in TABLES:
            policy_name = f"backend_only_{table}"

            # Drop existing policy if it exists (idempotent).
            db.execute(text(f"""
                DO $$ BEGIN
                    DROP POLICY IF EXISTS "{policy_name}" ON {table};
                END $$;
            """))

            # Create policy: deny all for non-service roles.
            # Using 'false' as the check means no rows are visible/writable.
            db.execute(text(f"""
                CREATE POLICY "{policy_name}" ON {table}
                    FOR ALL
                    USING (false)
                    WITH CHECK (false);
            """))
            print(f"  Policy '{policy_name}' created on '{table}' (deny all non-service access).")

        db.commit()
        print()

        # --- Step 4: Verify ---
        print("Verification — RLS status after changes:")
        for table in TABLES:
            result = db.execute(text(
                "SELECT relrowsecurity FROM pg_class WHERE relname = :table"
            ), {"table": table}).fetchone()
            status = "ENABLED" if result and result[0] else "DISABLED"

            policies = db.execute(text(
                "SELECT policyname FROM pg_policies WHERE tablename = :table"
            ), {"table": table}).fetchall()
            policy_names = [p[0] for p in policies]

            print(f"  {table}: {status}, policies: {policy_names}")

        print("\nRLS setup complete.")
        print("Note: Backend uses service_role key which bypasses RLS automatically.")

    except Exception as e:
        db.rollback()
        print(f"ERROR: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    enable_rls()
