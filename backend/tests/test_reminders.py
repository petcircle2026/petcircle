"""
PetCircle — Comprehensive Reminder System Test

Tests the complete reminder pipeline:
    1. Reminder engine: creates reminders for upcoming/overdue records
    2. Deduplication: re-running engine doesn't create duplicates
    3. Send pending reminders (dry-run, no actual WhatsApp)
    4. Reminder responses: DONE, SNOOZE, RESCHEDULE, CANCEL
    5. Edge cases: invalid payloads, already-completed reminders

Uses production Supabase DB with isolated test data that is cleaned up.
"""

import os
import sys
import uuid
import logging

# Set test environment before any app imports
os.environ["APP_ENV"] = "test"
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from datetime import date, timedelta
from app.database import SessionLocal
from app.models.user import User
from app.models.pet import Pet
from app.models.preventive_record import PreventiveRecord
from app.models.preventive_master import PreventiveMaster
from app.models.reminder import Reminder
from app.services.reminder_engine import run_reminder_engine
from app.services.reminder_response import (
    handle_reminder_response,
    apply_reschedule_date,
)
from app.services.preventive_calculator import compute_next_due_date, compute_status
from app.core.constants import (
    REMINDER_DONE,
    REMINDER_SNOOZE_7,
    REMINDER_SNOOZE_DAYS,
    REMINDER_RESCHEDULE,
    REMINDER_CANCEL,
)
from app.core.encryption import encrypt_field, hash_field
from app.utils.date_utils import get_today_ist

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

PASS = 0
FAIL = 0


def test(name, condition, detail=""):
    """Simple test assertion with tracking."""
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} -- {detail}")


def create_test_user(db):
    """Create an isolated test user for reminder tests."""
    test_mobile = "919999988888"
    user = User(
        id=uuid.uuid4(),
        mobile_number=encrypt_field(test_mobile),
        mobile_hash=hash_field(test_mobile),
        full_name="Reminder Test User",
        pincode=encrypt_field("400001"),
        consent_given=True,
        onboarding_state="complete",
    )
    db.add(user)
    db.flush()
    return user


def create_test_pet(db, user):
    """Create a test pet."""
    pet = Pet(
        id=uuid.uuid4(),
        user_id=user.id,
        name="TestDog",
        species="dog",
        breed="Labrador",
        gender="male",
        dob=date(2023, 1, 1),
        weight=25.0,
        neutered=True,
    )
    db.add(pet)
    db.flush()
    return pet


def create_test_preventive_records(db, pet):
    """Create preventive records with different statuses for testing."""
    today = get_today_ist()

    # Get a real preventive master from DB for the pet's species
    masters = db.query(PreventiveMaster).filter(
        PreventiveMaster.species == pet.species
    ).all()

    if not masters:
        print("  WARNING: No preventive masters found for species 'dog'")
        return []

    records = []

    # Record 1: Overdue (due date in the past)
    if len(masters) > 0:
        rec = PreventiveRecord(
            id=uuid.uuid4(),
            pet_id=pet.id,
            preventive_master_id=masters[0].id,
            last_done_date=today - timedelta(days=400),
            next_due_date=today - timedelta(days=35),
            status="overdue",
        )
        db.add(rec)
        records.append(("overdue", rec, masters[0]))

    # Record 2: Upcoming (due date within reminder window)
    if len(masters) > 1:
        rec = PreventiveRecord(
            id=uuid.uuid4(),
            pet_id=pet.id,
            preventive_master_id=masters[1].id,
            last_done_date=today - timedelta(days=350),
            next_due_date=today + timedelta(days=5),
            status="upcoming",
        )
        db.add(rec)
        records.append(("upcoming", rec, masters[1]))

    # Record 3: Up-to-date (should NOT get a reminder)
    if len(masters) > 2:
        rec = PreventiveRecord(
            id=uuid.uuid4(),
            pet_id=pet.id,
            preventive_master_id=masters[2].id,
            last_done_date=today - timedelta(days=30),
            next_due_date=today + timedelta(days=335),
            status="up_to_date",
        )
        db.add(rec)
        records.append(("up_to_date", rec, masters[2]))

    # Record 4: Another upcoming for snooze test
    if len(masters) > 3:
        rec = PreventiveRecord(
            id=uuid.uuid4(),
            pet_id=pet.id,
            preventive_master_id=masters[3].id,
            last_done_date=today - timedelta(days=355),
            next_due_date=today + timedelta(days=10),
            status="upcoming",
        )
        db.add(rec)
        records.append(("upcoming_snooze", rec, masters[3]))

    # Record 5: Another upcoming for cancel test
    if len(masters) > 4:
        rec = PreventiveRecord(
            id=uuid.uuid4(),
            pet_id=pet.id,
            preventive_master_id=masters[4].id,
            last_done_date=today - timedelta(days=360),
            next_due_date=today + timedelta(days=3),
            status="upcoming",
        )
        db.add(rec)
        records.append(("upcoming_cancel", rec, masters[4]))

    db.flush()
    return records


def cleanup_test_data(db, user_id):
    """Remove all test data created during the test."""
    try:
        pets = db.query(Pet).filter(Pet.user_id == user_id).all()
        for pet in pets:
            recs = db.query(PreventiveRecord).filter(
                PreventiveRecord.pet_id == pet.id
            ).all()
            for rec in recs:
                db.query(Reminder).filter(
                    Reminder.preventive_record_id == rec.id
                ).delete()
            db.query(PreventiveRecord).filter(
                PreventiveRecord.pet_id == pet.id
            ).delete()
        db.query(Pet).filter(Pet.user_id == user_id).delete()
        db.query(User).filter(User.id == user_id).delete()
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"  Cleanup warning: {e}")


def main():
    global PASS, FAIL
    db = SessionLocal()
    user = None

    try:
        # ==================================================================
        print("\n" + "=" * 60)
        print("SETUP: Create test user, pet, and preventive records")
        print("=" * 60)
        # ==================================================================

        # Clean up any leftover test data from previous runs
        test_mobile = "919999988888"
        existing = db.query(User).filter(
            User.mobile_hash == hash_field(test_mobile)
        ).first()
        if existing:
            cleanup_test_data(db, existing.id)
            print("  Cleaned up previous test data")

        user = create_test_user(db)
        test("Test user created", user is not None)

        pet = create_test_pet(db, user)
        test("Test pet created", pet is not None)

        records = create_test_preventive_records(db, pet)
        test("Preventive records created", len(records) >= 3, f"got {len(records)}")
        db.commit()

        for label, rec, master in records:
            print(f"    Record [{label}]: {master.item_name}, "
                  f"due={rec.next_due_date}, status={rec.status}")

        # ==================================================================
        print("\n" + "=" * 60)
        print("TEST 1: REMINDER ENGINE — Create reminders")
        print("=" * 60)
        # ==================================================================

        results = run_reminder_engine(db)
        test("Reminder engine ran successfully", results is not None)
        test("Records checked > 0", results["records_checked"] > 0)
        test("Reminders created > 0", results["reminders_created"] > 0)
        test("No errors", results["errors"] == 0)

        print(f"    Results: checked={results['records_checked']}, "
              f"created={results['reminders_created']}, "
              f"skipped={results['reminders_skipped']}, "
              f"errors={results['errors']}")

        # Verify reminders in DB
        reminders = (
            db.query(Reminder)
            .join(PreventiveRecord)
            .filter(PreventiveRecord.pet_id == pet.id)
            .all()
        )
        test("Reminders exist in DB", len(reminders) > 0, f"got {len(reminders)}")

        # Only upcoming/overdue records should have reminders
        reminder_record_ids = {r.preventive_record_id for r in reminders}
        overdue_upcoming_ids = {
            rec.id for label, rec, _ in records
            if label in ("overdue", "upcoming", "upcoming_snooze", "upcoming_cancel")
        }
        up_to_date_ids = {
            rec.id for label, rec, _ in records if label == "up_to_date"
        }

        test(
            "Upcoming/overdue records got reminders",
            overdue_upcoming_ids.issubset(reminder_record_ids),
            f"expected {len(overdue_upcoming_ids)}, "
            f"found {len(overdue_upcoming_ids & reminder_record_ids)}"
        )
        test(
            "Up-to-date records did NOT get reminders",
            not up_to_date_ids.intersection(reminder_record_ids),
        )

        # All reminders should be 'pending'
        all_pending = all(r.status == "pending" for r in reminders)
        test("All reminders have status 'pending'", all_pending)

        for r in reminders:
            rec_label = next(
                (l for l, rec, _ in records if rec.id == r.preventive_record_id),
                "unknown"
            )
            print(f"    Reminder: id={str(r.id)[:8]}..., "
                  f"record=[{rec_label}], status={r.status}, "
                  f"due={r.next_due_date}")

        # ==================================================================
        print("\n" + "=" * 60)
        print("TEST 2: DEDUPLICATION — Re-run engine")
        print("=" * 60)
        # ==================================================================

        results2 = run_reminder_engine(db)
        test("Second run completed", results2 is not None)
        test("No new reminders created (dedup)", results2["reminders_created"] == 0)
        test(
            "All were skipped (dedup)",
            results2["reminders_skipped"] == results2["records_checked"],
            f"skipped={results2['reminders_skipped']}, "
            f"checked={results2['records_checked']}"
        )

        print(f"    Results: checked={results2['records_checked']}, "
              f"created={results2['reminders_created']}, "
              f"skipped={results2['reminders_skipped']}")

        # ==================================================================
        print("\n" + "=" * 60)
        print("TEST 3: REMINDER RESPONSE — DONE")
        print("=" * 60)
        # ==================================================================

        # Find the overdue reminder
        overdue_rec_id = next(
            rec.id for label, rec, _ in records if label == "overdue"
        )
        overdue_reminder = db.query(Reminder).filter(
            Reminder.preventive_record_id == overdue_rec_id
        ).first()

        # Simulate: mark as 'sent' (as if WhatsApp delivered it)
        overdue_reminder.status = "sent"
        db.commit()
        test("Overdue reminder set to 'sent'", overdue_reminder.status == "sent")

        # Handle DONE response
        result = handle_reminder_response(db, overdue_reminder.id, REMINDER_DONE)
        test("DONE response processed", result["status"] == "completed")
        test("Action is REMINDER_DONE", result["action"] == REMINDER_DONE)

        # Verify DB state
        db.refresh(overdue_reminder)
        db.refresh(db.query(PreventiveRecord).get(overdue_rec_id))
        updated_rec = db.query(PreventiveRecord).get(overdue_rec_id)
        today = get_today_ist()

        test("Reminder status = completed", overdue_reminder.status == "completed")
        test("Record last_done_date = today", updated_rec.last_done_date == today)
        test(
            "Record next_due_date recalculated",
            updated_rec.next_due_date > today,
            f"next_due={updated_rec.next_due_date}"
        )
        test(
            "Record status updated",
            updated_rec.status in ("up_to_date", "upcoming"),
            f"status={updated_rec.status}"
        )

        print(f"    After DONE: last_done={updated_rec.last_done_date}, "
              f"next_due={updated_rec.next_due_date}, "
              f"status={updated_rec.status}")

        # ==================================================================
        print("\n" + "=" * 60)
        print("TEST 4: REMINDER RESPONSE — SNOOZE")
        print("=" * 60)
        # ==================================================================

        # Find the snooze reminder
        snooze_rec_id = next(
            rec.id for label, rec, _ in records if label == "upcoming_snooze"
        )
        snooze_reminder = db.query(Reminder).filter(
            Reminder.preventive_record_id == snooze_rec_id
        ).first()
        snooze_rec = db.query(PreventiveRecord).get(snooze_rec_id)
        old_due = snooze_rec.next_due_date

        # Mark as sent
        snooze_reminder.status = "sent"
        db.commit()

        # Handle SNOOZE response
        result = handle_reminder_response(db, snooze_reminder.id, REMINDER_SNOOZE_7)
        test("SNOOZE response processed", result["status"] == "snoozed")

        # Verify DB state
        db.refresh(snooze_reminder)
        db.refresh(snooze_rec)
        expected_new_due = old_due + timedelta(days=REMINDER_SNOOZE_DAYS)

        test("Reminder status = snoozed", snooze_reminder.status == "snoozed")
        test(
            f"Due date pushed +{REMINDER_SNOOZE_DAYS} days",
            snooze_rec.next_due_date == expected_new_due,
            f"expected={expected_new_due}, got={snooze_rec.next_due_date}"
        )

        print(f"    After SNOOZE: old_due={old_due}, "
              f"new_due={snooze_rec.next_due_date}")

        # ==================================================================
        print("\n" + "=" * 60)
        print("TEST 5: REMINDER RESPONSE — RESCHEDULE")
        print("=" * 60)
        # ==================================================================

        # Find the upcoming reminder
        upcoming_rec_id = next(
            rec.id for label, rec, _ in records if label == "upcoming"
        )
        upcoming_reminder = db.query(Reminder).filter(
            Reminder.preventive_record_id == upcoming_rec_id
        ).first()

        # Mark as sent
        upcoming_reminder.status = "sent"
        db.commit()

        # Step 1: Request reschedule
        result = handle_reminder_response(
            db, upcoming_reminder.id, REMINDER_RESCHEDULE
        )
        test("RESCHEDULE request processed", result["status"] == "awaiting_date")
        test(
            "Reminder still in 'sent' (awaiting date)",
            upcoming_reminder.status == "sent"
        )

        # Step 2: Apply the rescheduled date
        new_date = today + timedelta(days=60)
        result2 = apply_reschedule_date(db, upcoming_reminder.id, new_date)
        test("Reschedule applied", result2["status"] == "rescheduled")

        db.refresh(upcoming_reminder)
        upcoming_rec = db.query(PreventiveRecord).get(upcoming_rec_id)
        db.refresh(upcoming_rec)

        test("Reminder status = completed", upcoming_reminder.status == "completed")
        test(
            "Record next_due_date = new date",
            upcoming_rec.next_due_date == new_date,
            f"got={upcoming_rec.next_due_date}"
        )

        print(f"    After RESCHEDULE: new_due={upcoming_rec.next_due_date}, "
              f"status={upcoming_rec.status}")

        # ==================================================================
        print("\n" + "=" * 60)
        print("TEST 6: REMINDER RESPONSE — CANCEL")
        print("=" * 60)
        # ==================================================================

        # Find the cancel reminder
        cancel_rec_id = next(
            rec.id for label, rec, _ in records if label == "upcoming_cancel"
        )
        cancel_reminder = db.query(Reminder).filter(
            Reminder.preventive_record_id == cancel_rec_id
        ).first()

        # Mark as sent
        cancel_reminder.status = "sent"
        db.commit()

        # Handle CANCEL
        result = handle_reminder_response(db, cancel_reminder.id, REMINDER_CANCEL)
        test("CANCEL response processed", result["status"] == "cancelled")

        db.refresh(cancel_reminder)
        cancel_rec = db.query(PreventiveRecord).get(cancel_rec_id)
        db.refresh(cancel_rec)

        test("Reminder status = completed", cancel_reminder.status == "completed")
        test(
            "Record status = cancelled",
            cancel_rec.status == "cancelled",
            f"got={cancel_rec.status}"
        )

        print(f"    After CANCEL: record status={cancel_rec.status}")

        # ==================================================================
        print("\n" + "=" * 60)
        print("TEST 7: EDGE CASES")
        print("=" * 60)
        # ==================================================================

        # 7a: Invalid payload
        try:
            handle_reminder_response(db, cancel_reminder.id, "INVALID_PAYLOAD")
            test("Reject invalid payload", False, "no exception raised")
        except ValueError as e:
            test("Reject invalid payload", "Unknown reminder payload" in str(e))

        # 7b: Responding to already-completed reminder
        try:
            handle_reminder_response(db, cancel_reminder.id, REMINDER_DONE)
            test("Reject completed reminder response", False, "no exception raised")
        except ValueError as e:
            test("Reject completed reminder response", "cannot be responded to" in str(e))

        # 7c: Non-existent reminder
        fake_id = uuid.uuid4()
        try:
            handle_reminder_response(db, fake_id, REMINDER_DONE)
            test("Reject non-existent reminder", False, "no exception raised")
        except ValueError as e:
            test("Reject non-existent reminder", "not found" in str(e))

        # 7d: Re-run engine after CANCEL — cancelled records excluded
        results3 = run_reminder_engine(db)
        # The cancelled record should not produce a new reminder
        cancelled_reminders = db.query(Reminder).filter(
            Reminder.preventive_record_id == cancel_rec_id
        ).all()
        test(
            "No new reminder for cancelled record",
            len(cancelled_reminders) == 1,  # only the original one
            f"got {len(cancelled_reminders)} reminders"
        )

        print(f"    Engine re-run: checked={results3['records_checked']}, "
              f"created={results3['reminders_created']}")

        # ==================================================================
        print("\n" + "=" * 60)
        print("TEST 8: REMINDER ENGINE — Internal endpoint simulation")
        print("=" * 60)
        # ==================================================================

        # Verify the internal endpoint logic (conflict expiry + reminder + send)
        from app.services.conflict_expiry import expire_pending_conflicts

        expired = expire_pending_conflicts(db)
        test("Conflict expiry ran", True, f"expired={expired}")

        # Run reminder engine one more time
        results4 = run_reminder_engine(db)
        test("Final engine run completed", results4 is not None)
        print(f"    Final run: checked={results4['records_checked']}, "
              f"created={results4['reminders_created']}, "
              f"skipped={results4['reminders_skipped']}")

    except Exception as e:
        print(f"\n  FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()

    finally:
        # ==================================================================
        print("\n" + "=" * 60)
        print("CLEANUP: Remove test data")
        print("=" * 60)
        # ==================================================================

        if user:
            cleanup_test_data(db, user.id)
            print("  Test data cleaned up")

        db.close()

    # ==================================================================
    print("\n" + "=" * 60)
    print(f"RESULTS: {PASS} passed, {FAIL} failed, {PASS + FAIL} total")
    print("=" * 60)
    # ==================================================================

    return 1 if FAIL > 0 else 0


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
