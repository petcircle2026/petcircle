"""
PetCircle — Seed Reminder Trigger Test Data

Creates a complete user + pet + preventive records for +919095705762
so that the reminder engine triggers ALL types of reminders:

    1. OVERDUE reminders   — items past their due date (sends overdue template)
    2. UPCOMING reminders  — items due within the reminder window (sends reminder template)
    3. UP_TO_DATE control  — items not due yet (should NOT trigger)
    4. Deduplication       — re-running should create 0 new reminders
"""

import os
import sys
import uuid
import logging

os.environ["APP_ENV"] = "production"
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from datetime import date, timedelta
from app.database import SessionLocal
from app.models.user import User
from app.models.pet import Pet
from app.models.preventive_record import PreventiveRecord
from app.models.preventive_master import PreventiveMaster
from app.models.reminder import Reminder
from app.core.encryption import encrypt_field, hash_field
from app.utils.date_utils import get_today_ist

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

PHONE = "919095705762"
TODAY = get_today_ist()


def main():
    db = SessionLocal()

    try:
        # =================================================================
        print("=" * 60)
        print("STEP 1: Find or create user +919095705762")
        print("=" * 60)
        # =================================================================

        mobile_hash = hash_field(PHONE)
        user = db.query(User).filter(User.mobile_hash == mobile_hash).first()

        if user:
            print(f"  User already exists: id={user.id}, name={user.full_name}")
        else:
            user = User(
                id=uuid.uuid4(),
                mobile_number=encrypt_field(PHONE),
                mobile_hash=mobile_hash,
                full_name="PetCircle Tester",
                pincode=encrypt_field("600001"),
                consent_given=True,
                onboarding_state="complete",
            )
            db.add(user)
            db.flush()
            print(f"  Created user: id={user.id}, name={user.full_name}")

        # =================================================================
        print("\n" + "=" * 60)
        print("STEP 2: Find or create pet")
        print("=" * 60)
        # =================================================================

        pet = db.query(Pet).filter(
            Pet.user_id == user.id,
            Pet.is_deleted == False,
        ).first()

        if pet:
            print(f"  Pet already exists: id={pet.id}, name={pet.name}, species={pet.species}")
        else:
            pet = Pet(
                id=uuid.uuid4(),
                user_id=user.id,
                name="Bruno",
                species="dog",
                breed="Golden Retriever",
                gender="male",
                dob=date(2023, 6, 15),
                weight=28.0,
                neutered=True,
            )
            db.add(pet)
            db.flush()
            print(f"  Created pet: id={pet.id}, name={pet.name}, species={pet.species}")

        # =================================================================
        print("\n" + "=" * 60)
        print("STEP 3: Load preventive masters")
        print("=" * 60)
        # =================================================================

        masters = db.query(PreventiveMaster).filter(
            PreventiveMaster.species == pet.species,
        ).all()

        print(f"  Found {len(masters)} preventive masters for '{pet.species}':")
        for m in masters:
            print(f"    - {m.item_name} (recurrence={m.recurrence_days}d, "
                  f"remind_before={m.reminder_before_days}d, "
                  f"category={m.category})")

        if len(masters) < 3:
            print("  ERROR: Need at least 3 preventive masters to test all triggers.")
            return

        # =================================================================
        print("\n" + "=" * 60)
        print("STEP 4: Clear existing records & reminders for this pet")
        print("=" * 60)
        # =================================================================

        existing_recs = db.query(PreventiveRecord).filter(
            PreventiveRecord.pet_id == pet.id,
        ).all()

        cleared_reminders = 0
        for rec in existing_recs:
            count = db.query(Reminder).filter(
                Reminder.preventive_record_id == rec.id,
            ).delete()
            cleared_reminders += count

        cleared_records = db.query(PreventiveRecord).filter(
            PreventiveRecord.pet_id == pet.id,
        ).delete()

        db.commit()
        print(f"  Cleared {cleared_records} records, {cleared_reminders} reminders")

        # =================================================================
        print("\n" + "=" * 60)
        print("STEP 5: Create preventive records to trigger ALL reminder types")
        print("=" * 60)
        # =================================================================

        # Layout:
        #   Record 0: OVERDUE (due 10 days ago)      → triggers overdue template
        #   Record 1: OVERDUE (due 30 days ago)      → triggers overdue template
        #   Record 2: UPCOMING (due in 3 days)       → triggers reminder template
        #   Record 3: UPCOMING (due tomorrow)         → triggers reminder template
        #   Record 4: UP_TO_DATE (due in 300 days)   → control, NO trigger
        #   Remaining: UPCOMING with varying windows

        scenarios = []

        # --- OVERDUE triggers ---
        if len(masters) > 0:
            scenarios.append({
                "master": masters[0],
                "status": "overdue",
                "next_due_date": TODAY - timedelta(days=10),
                "last_done_date": TODAY - timedelta(days=375),
                "label": f"OVERDUE  — {masters[0].item_name} (10 days late)",
            })

        if len(masters) > 1:
            scenarios.append({
                "master": masters[1],
                "status": "overdue",
                "next_due_date": TODAY - timedelta(days=30),
                "last_done_date": TODAY - timedelta(days=395),
                "label": f"OVERDUE  — {masters[1].item_name} (30 days late)",
            })

        # --- UPCOMING triggers ---
        if len(masters) > 2:
            scenarios.append({
                "master": masters[2],
                "status": "upcoming",
                "next_due_date": TODAY + timedelta(days=3),
                "last_done_date": TODAY - timedelta(days=362),
                "label": f"UPCOMING — {masters[2].item_name} (due in 3 days)",
            })

        if len(masters) > 3:
            scenarios.append({
                "master": masters[3],
                "status": "upcoming",
                "next_due_date": TODAY + timedelta(days=1),
                "last_done_date": TODAY - timedelta(days=364),
                "label": f"UPCOMING — {masters[3].item_name} (due TOMORROW)",
            })

        # --- CONTROL (no trigger) ---
        if len(masters) > 4:
            scenarios.append({
                "master": masters[4],
                "status": "up_to_date",
                "next_due_date": TODAY + timedelta(days=300),
                "last_done_date": TODAY - timedelta(days=65),
                "label": f"CONTROL  — {masters[4].item_name} (no trigger, due in 300d)",
            })

        # --- Additional UPCOMING for remaining masters ---
        for i, m in enumerate(masters[5:], start=5):
            scenarios.append({
                "master": m,
                "status": "upcoming",
                "next_due_date": TODAY + timedelta(days=2 + i),
                "last_done_date": TODAY - timedelta(days=363),
                "label": f"UPCOMING — {m.item_name} (due in {2 + i} days)",
            })

        created_records = []
        for s in scenarios:
            rec = PreventiveRecord(
                id=uuid.uuid4(),
                pet_id=pet.id,
                preventive_master_id=s["master"].id,
                last_done_date=s["last_done_date"],
                next_due_date=s["next_due_date"],
                status=s["status"],
            )
            db.add(rec)
            created_records.append((s, rec))
            print(f"  [{s['status'].upper():11}] {s['label']}")

        db.commit()
        print(f"\n  Created {len(created_records)} preventive records")

        # =================================================================
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        # =================================================================

        overdue_count = sum(1 for s, _ in created_records if s["status"] == "overdue")
        upcoming_count = sum(1 for s, _ in created_records if s["status"] == "upcoming")
        control_count = sum(1 for s, _ in created_records if s["status"] == "up_to_date")

        print(f"""
  User:     {user.full_name} (+91 9095705762)
  Pet:      {pet.name} ({pet.species}, {pet.breed})

  Records created:
    {overdue_count} OVERDUE   → will send {overdue_count} overdue WhatsApp template(s)
    {upcoming_count} UPCOMING  → will send {upcoming_count} reminder WhatsApp template(s)
    {control_count} UP_TO_DATE → control, NO messages

  Total WhatsApp messages expected: {overdue_count + upcoming_count}

  To trigger the reminder engine NOW:

    curl -X POST https://pet-circle.onrender.com/internal/run-reminder-engine \\
      -H "X-ADMIN-KEY: 48e9892005061081d7afdc4f3562c680ee8188d990e89b669ee295121e6e776c"

  Or wait for the 8 AM IST daily cron.
""")

    except Exception as e:
        db.rollback()
        print(f"\n  FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()

    finally:
        db.close()


if __name__ == "__main__":
    main()
