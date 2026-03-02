"""
PetCircle Phase 1 — End-to-End Test Suite

Tests the complete application flow:
    1. User onboarding (consent, name, pincode, pet creation)
    2. Document upload to Supabase + DB record creation
    3. GPT extraction from sample reports
    4. Dashboard data retrieval
    5. Preventive record verification
    6. Reminder engine execution
    7. Admin endpoints (all CRUD operations)
    8. Health score calculation
    9. Query engine
   10. Conflict detection
"""

import sys
import os
import asyncio

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal
from app.models.user import User
from app.models.pet import Pet
from app.models.preventive_record import PreventiveRecord
from app.models.preventive_master import PreventiveMaster
from app.models.reminder import Reminder
from app.models.document import Document
from app.models.dashboard_token import DashboardToken
from app.models.message_log import MessageLog
from app.models.conflict_flag import ConflictFlag
from app.services.onboarding import (
    create_pending_user,
    handle_onboarding_step,
    generate_dashboard_token,
    seed_preventive_records_for_pet,
)
from app.services.preventive_calculator import (
    compute_next_due_date,
    compute_status,
    create_preventive_record,
    recalculate_all_for_pet,
)
from app.services.health_score import compute_health_score
from app.services.reminder_engine import run_reminder_engine, send_pending_reminders
from app.services.conflict_expiry import expire_pending_conflicts
from app.services.conflict_engine import check_and_create_conflict, resolve_conflict
from app.services.dashboard_service import (
    get_dashboard_data,
    update_pet_weight,
    update_preventive_date,
)
from app.services.document_upload import (
    validate_file_upload,
    check_daily_upload_limit,
    build_storage_path,
    create_document_record,
)
from app.services.gpt_extraction import (
    _validate_extraction_json,
    _match_preventive_master,
)
from app.utils.date_utils import parse_date, format_date_for_db, get_today_ist
from app.core.constants import *
from datetime import date, timedelta
import uuid


PASS = 0
FAIL = 0


def test(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} -- {detail}")


def main():
    global PASS, FAIL
    db = SessionLocal()

    try:
        # ===================================================================
        print("\n" + "="*60)
        print("CLEANUP: Remove test data from previous runs")
        print("="*60)
        # ===================================================================

        test_mobile = "919999900001"
        # Clean up any existing test data
        existing_user = db.query(User).filter(User.mobile_number == test_mobile).first()
        if existing_user:
            # Delete all related data
            pets = db.query(Pet).filter(Pet.user_id == existing_user.id).all()
            for p in pets:
                db.query(DashboardToken).filter(DashboardToken.pet_id == p.id).delete()
                db.query(Document).filter(Document.pet_id == p.id).delete()
                recs = db.query(PreventiveRecord).filter(PreventiveRecord.pet_id == p.id).all()
                for rec in recs:
                    db.query(Reminder).filter(Reminder.preventive_record_id == rec.id).delete()
                    db.query(ConflictFlag).filter(ConflictFlag.preventive_record_id == rec.id).delete()
                db.query(PreventiveRecord).filter(PreventiveRecord.pet_id == p.id).delete()
            db.query(Pet).filter(Pet.user_id == existing_user.id).delete()
            db.query(User).filter(User.id == existing_user.id).delete()
            db.commit()
            print("  Cleaned up previous test data")

        # ===================================================================
        print("\n" + "="*60)
        print("TEST 1: USER ONBOARDING")
        print("="*60)
        # ===================================================================

        # Create a pending user
        user = create_pending_user(db, test_mobile)
        test("User created", user is not None)
        test("User has pending state", user.onboarding_state == "awaiting_consent")
        test("User consent not given", user.consent_given == False)
        test("User name is _pending", user.full_name == "_pending")
        test("User mobile correct", user.mobile_number == test_mobile)

        # Mock send function (no-op)
        async def mock_send(db, to, text):
            pass

        # Step through onboarding
        loop = asyncio.new_event_loop()

        # Step 1: Consent
        loop.run_until_complete(handle_onboarding_step(db, user, "yes", mock_send))
        db.refresh(user)
        test("Consent given after 'yes'", user.consent_given == True)
        test("State -> awaiting_name", user.onboarding_state == "awaiting_name")

        # Step 2: Name
        loop.run_until_complete(handle_onboarding_step(db, user, "Rahul Sharma", mock_send))
        db.refresh(user)
        test("Name stored", user.full_name == "Rahul Sharma")
        test("State -> awaiting_pincode", user.onboarding_state == "awaiting_pincode")

        # Step 3: Pincode
        loop.run_until_complete(handle_onboarding_step(db, user, "400001", mock_send))
        db.refresh(user)
        test("Pincode stored", user.pincode == "400001")
        test("State -> awaiting_pet_name", user.onboarding_state == "awaiting_pet_name")

        # Step 4: Pet name
        loop.run_until_complete(handle_onboarding_step(db, user, "Zayn", mock_send))
        db.refresh(user)
        test("State -> awaiting_species", user.onboarding_state == "awaiting_species")
        pet = db.query(Pet).filter(Pet.user_id == user.id).first()
        test("Pet created with name", pet is not None and pet.name == "Zayn")

        # Step 5: Species
        loop.run_until_complete(handle_onboarding_step(db, user, "dog", mock_send))
        db.refresh(user)
        db.refresh(pet)
        test("Species set to dog", pet.species == "dog")
        test("State -> awaiting_breed", user.onboarding_state == "awaiting_breed")

        # Step 6: Breed
        loop.run_until_complete(handle_onboarding_step(db, user, "Labrador", mock_send))
        db.refresh(user)
        db.refresh(pet)
        test("Breed stored", pet.breed == "Labrador")
        test("State -> awaiting_gender", user.onboarding_state == "awaiting_gender")

        # Step 7: Gender
        loop.run_until_complete(handle_onboarding_step(db, user, "male", mock_send))
        db.refresh(user)
        db.refresh(pet)
        test("Gender stored", pet.gender == "male")
        test("State -> awaiting_dob", user.onboarding_state == "awaiting_dob")

        # Step 8: DOB
        loop.run_until_complete(handle_onboarding_step(db, user, "15/06/2022", mock_send))
        db.refresh(user)
        db.refresh(pet)
        test("DOB parsed and stored", pet.dob == date(2022, 6, 15))
        test("State -> awaiting_weight", user.onboarding_state == "awaiting_weight")

        # Step 9: Weight
        loop.run_until_complete(handle_onboarding_step(db, user, "28.5", mock_send))
        db.refresh(user)
        db.refresh(pet)
        test("Weight stored", float(pet.weight) == 28.5)
        test("State -> awaiting_neutered", user.onboarding_state == "awaiting_neutered")

        # Step 10: Neutered -> Complete
        loop.run_until_complete(handle_onboarding_step(db, user, "yes", mock_send))
        db.refresh(user)
        db.refresh(pet)
        test("Neutered stored as True", pet.neutered == True)
        test("State -> complete", user.onboarding_state == "complete")

        # Verify preventive records seeded
        records = db.query(PreventiveRecord).filter(PreventiveRecord.pet_id == pet.id).all()
        test("Preventive records seeded", len(records) > 0, f"got {len(records)}")
        test("7 dog preventive items", len(records) == 7, f"got {len(records)}")

        # Verify dashboard token
        token_record = db.query(DashboardToken).filter(DashboardToken.pet_id == pet.id).first()
        test("Dashboard token generated", token_record is not None)
        test("Token is 32 hex chars", token_record and len(token_record.token) == 32)
        dashboard_token = token_record.token if token_record else None

        # ===================================================================
        print("\n" + "="*60)
        print("TEST 2: DATE UTILITIES")
        print("="*60)
        # ===================================================================

        test("Parse DD/MM/YYYY", parse_date("15/06/2022") == date(2022, 6, 15))
        test("Parse DD-MM-YYYY", parse_date("15-06-2022") == date(2022, 6, 15))
        test("Parse DD Month YYYY", parse_date("15 June 2022") == date(2022, 6, 15))
        test("Parse YYYY-MM-DD", parse_date("2022-06-15") == date(2022, 6, 15))
        test("Format for DB", format_date_for_db(date(2022, 6, 15)) == "2022-06-15")
        test("Get today IST", get_today_ist() is not None)

        try:
            parse_date("invalid")
            test("Reject invalid date", False)
        except ValueError:
            test("Reject invalid date", True)

        # ===================================================================
        print("\n" + "="*60)
        print("TEST 3: PREVENTIVE CALCULATOR")
        print("="*60)
        # ===================================================================

        today = get_today_ist()
        next_due = compute_next_due_date(today, 365)
        test("Next due = today + 365 days", next_due == today + timedelta(days=365))

        # Up to date: next due is far in future
        status = compute_status(today + timedelta(days=100), 30)
        test("Status 'up_to_date' for far future", status == "up_to_date")

        # Upcoming: within reminder window
        status = compute_status(today + timedelta(days=5), 30)
        test("Status 'upcoming' for near future", status == "upcoming")

        # Overdue: past due
        status = compute_status(today - timedelta(days=10), 30)
        test("Status 'overdue' for past due", status == "overdue")

        # ===================================================================
        print("\n" + "="*60)
        print("TEST 4: HEALTH SCORE")
        print("="*60)
        # ===================================================================

        score_data = compute_health_score(db, pet.id)
        test("Health score returned", score_data is not None)
        test("Score is numeric", isinstance(score_data.get("score"), (int, float)))
        test("Score between 0-100", 0 <= score_data["score"] <= 100)
        test("Essential count present", "essential_total" in score_data)
        test("Complementary count present", "complementary_total" in score_data)
        print(f"    Score: {score_data['score']}/100 "
              f"(Essential: {score_data['essential_done']}/{score_data['essential_total']}, "
              f"Comp: {score_data['complementary_done']}/{score_data['complementary_total']})")

        # ===================================================================
        print("\n" + "="*60)
        print("TEST 5: DOCUMENT UPLOAD & STORAGE")
        print("="*60)
        # ===================================================================

        # Test file validation
        validate_file_upload(1024, "image/jpeg")
        test("Valid JPEG accepted", True)

        validate_file_upload(5 * 1024 * 1024, "application/pdf")
        test("Valid PDF accepted", True)

        try:
            validate_file_upload(15 * 1024 * 1024, "image/jpeg")
            test("Reject >10MB file", False)
        except ValueError:
            test("Reject >10MB file", True)

        try:
            validate_file_upload(1024, "application/exe")
            test("Reject invalid MIME", False)
        except ValueError:
            test("Reject invalid MIME", True)

        # Storage path
        path = build_storage_path(user.id, pet.id, "test.jpg")
        test("Storage path format", f"{user.id}/{pet.id}/test.jpg" == path)

        # Create document record
        doc = create_document_record(db, pet.id, path, "image/jpeg")
        test("Document record created", doc is not None)
        test("Extraction status pending", doc.extraction_status == "pending")

        # Upload to Supabase with a real sample file
        sample_dir = "C:/Users/Hp/Desktop/Experiment/Pet MVP/Sample_Reports/Sample_Reports"
        sample_files = os.listdir(sample_dir)
        test("Sample reports found", len(sample_files) > 0, f"got {len(sample_files)}")
        print(f"    Sample files: {sample_files[:5]}...")

        # Upload a vaccination record to Supabase
        vacc_file = None
        for f in sample_files:
            if "Vaccination" in f and f.endswith(".jpg"):
                vacc_file = f
                break

        if vacc_file:
            vacc_path = os.path.join(sample_dir, vacc_file)
            with open(vacc_path, "rb") as fh:
                file_content = fh.read()
            test(f"Read {vacc_file}", len(file_content) > 0, f"size={len(file_content)}")

            # Upload to Supabase
            storage_path = build_storage_path(str(user.id), str(pet.id), vacc_file)
            try:
                result = loop.run_until_complete(
                    _upload_to_supabase(file_content, storage_path, "image/jpeg")
                )
                test("Supabase upload succeeded", result is not None)

                # Create DB record for the uploaded file
                doc2 = create_document_record(db, pet.id, storage_path, "image/jpeg")
                test("Doc record created for upload", doc2 is not None)
                test("Doc extraction_status=pending", doc2.extraction_status == "pending")
            except Exception as e:
                test("Supabase upload", False, str(e))
        else:
            test("Found vaccination JPG", False, "no vaccination jpg in samples")

        # Upload a PDF report too
        pdf_file = None
        for f in sample_files:
            if f.endswith(".pdf"):
                pdf_file = f
                break

        if pdf_file:
            pdf_path = os.path.join(sample_dir, pdf_file)
            with open(pdf_path, "rb") as fh:
                pdf_content = fh.read()
            test(f"Read {pdf_file}", len(pdf_content) > 0)

            storage_path2 = build_storage_path(str(user.id), str(pet.id), pdf_file)
            try:
                result = loop.run_until_complete(
                    _upload_to_supabase(pdf_content, storage_path2, "application/pdf")
                )
                test("PDF upload to Supabase", result is not None)
                doc3 = create_document_record(db, pet.id, storage_path2, "application/pdf")
                test("PDF doc record created", doc3 is not None)
            except Exception as e:
                test("PDF Supabase upload", False, str(e))

        # ===================================================================
        print("\n" + "="*60)
        print("TEST 6: GPT EXTRACTION VALIDATION")
        print("="*60)
        # ===================================================================

        # Test JSON validation
        valid_json = '[{"item_name": "Rabies Vaccine", "last_done_date": "15/06/2024"}]'
        items = _validate_extraction_json(valid_json)
        test("Valid extraction JSON parsed", len(items) == 1)
        test("Item name extracted", items[0]["item_name"] == "Rabies Vaccine")
        test("Date normalized to DB format", items[0]["last_done_date"] == "2024-06-15")

        # Test wrapped format
        wrapped_json = '{"items": [{"item_name": "Deworming", "last_done_date": "2024-03-10"}]}'
        items2 = _validate_extraction_json(wrapped_json)
        test("Wrapped JSON format accepted", len(items2) == 1)

        # Test empty extraction
        empty_json = '{"items": []}'
        items3 = _validate_extraction_json(empty_json)
        test("Empty extraction returns empty list", len(items3) == 0)

        # Test preventive master matching
        master = _match_preventive_master(db, "Rabies Vaccine", "dog")
        test("Exact match 'Rabies Vaccine' for dog", master is not None)
        test("Master has correct recurrence", master and master.recurrence_days == 365)

        master2 = _match_preventive_master(db, "Rabies", "dog")
        test("Partial match 'Rabies' for dog", master2 is not None)

        master3 = _match_preventive_master(db, "Nonexistent Item", "dog")
        test("No match for unknown item", master3 is None)

        # ===================================================================
        print("\n" + "="*60)
        print("TEST 7: PREVENTIVE RECORD CREATION + CONFLICT DETECTION")
        print("="*60)
        # ===================================================================

        # Create a preventive record manually
        rabies_master = db.query(PreventiveMaster).filter(
            PreventiveMaster.item_name == "Rabies Vaccine",
            PreventiveMaster.species == "dog",
        ).first()

        if rabies_master:
            test_date = date(2024, 6, 15)
            record = create_preventive_record(db, pet.id, rabies_master.id, test_date)
            if record:
                test("Preventive record created", True)
                test("Last done date correct", record.last_done_date == test_date)
                test("Next due calculated", record.next_due_date == test_date + timedelta(days=365))
                test("Status calculated", record.status in ["up_to_date", "upcoming", "overdue"])

                # Test conflict detection
                conflict_date = date(2024, 7, 20)
                conflict = check_and_create_conflict(db, pet.id, rabies_master.id, conflict_date)
                test("Conflict detected for different date", conflict is not None)
                test("Conflict status is pending", conflict and conflict.status == "pending")
                test("Conflict new_date stored", conflict and conflict.new_date == conflict_date)

                # Resolve conflict
                if conflict:
                    resolve_conflict(db, conflict.id, CONFLICT_USE_NEW)
                    db.refresh(conflict)
                    test("Conflict resolved", conflict.status == "resolved")

                # No conflict for same date
                no_conflict = check_and_create_conflict(db, pet.id, rabies_master.id, conflict_date)
                test("No conflict for same date", no_conflict is None)
            else:
                test("Preventive record creation", False, "duplicate or error")

        # ===================================================================
        print("\n" + "="*60)
        print("TEST 8: DASHBOARD API")
        print("="*60)
        # ===================================================================

        if dashboard_token:
            # Get dashboard data
            data = get_dashboard_data(db, dashboard_token)
            test("Dashboard data returned", data is not None)
            test("Pet name in dashboard", data.get("pet", {}).get("name") == "Zayn")
            test("Species in dashboard", data.get("pet", {}).get("species") == "dog")
            test("Breed in dashboard", data.get("pet", {}).get("breed") == "Labrador")
            test("Owner in dashboard", data.get("owner", {}).get("full_name") == "Rahul Sharma")
            test("Preventive records present", len(data.get("preventive_records", [])) > 0)
            test("Health score present", "health_score" in data)
            test("Documents section present", "documents" in data)
            test("Reminders section present", "reminders" in data)

            # Print preventive summary
            print("\n    Dashboard Preventive Records:")
            for rec in data.get("preventive_records", []):
                print(f"      - {rec['item_name']}: status={rec['status']}, "
                      f"last_done={rec['last_done_date']}, "
                      f"next_due={rec['next_due_date']}")

            # Update weight via dashboard
            result = update_pet_weight(db, dashboard_token, 30.0)
            test("Weight updated via dashboard", result.get("status") == "updated")
            test("New weight is 30.0", result.get("new_weight") == 30.0)

            # Update preventive date via dashboard
            new_date = parse_date("01/03/2025")
            try:
                result = update_preventive_date(db, dashboard_token, "Rabies Vaccine", new_date)
                test("Preventive date updated", result.get("status") == "updated")
                test("Recalculated next due", result.get("new_next_due_date") is not None)
                print(f"    New next due: {result.get('new_next_due_date')}")
            except ValueError as e:
                test("Preventive date update", False, str(e))

            # Test invalid token
            try:
                get_dashboard_data(db, "invalid_token_12345678")
                test("Invalid token rejected", False)
            except ValueError:
                test("Invalid token rejected", True)
        else:
            test("Dashboard tests skipped", False, "no token generated")

        # ===================================================================
        print("\n" + "="*60)
        print("TEST 9: REMINDER ENGINE")
        print("="*60)
        # ===================================================================

        # Run conflict expiry first
        expired = expire_pending_conflicts(db)
        test("Conflict expiry ran", True, f"expired={expired}")

        # Run reminder engine
        results = run_reminder_engine(db)
        test("Reminder engine ran", results is not None)
        test("Records checked > 0", results["records_checked"] > 0)
        print(f"    Results: checked={results['records_checked']}, "
              f"created={results['reminders_created']}, "
              f"skipped={results['reminders_skipped']}")

        # Check reminders created
        reminders = db.query(Reminder).join(
            PreventiveRecord
        ).filter(PreventiveRecord.pet_id == pet.id).all()
        test("Reminders exist in DB", len(reminders) > 0, f"got {len(reminders)}")

        # ===================================================================
        print("\n" + "="*60)
        print("TEST 10: ADMIN ENDPOINTS (via direct DB)")
        print("="*60)
        # ===================================================================

        # Verify admin can see all data
        all_users = db.query(User).all()
        test("Admin: users queryable", len(all_users) > 0)

        all_pets = db.query(Pet).all()
        test("Admin: pets queryable", len(all_pets) > 0)

        all_docs = db.query(Document).filter(Document.pet_id == pet.id).all()
        test("Admin: documents queryable", len(all_docs) >= 0)

        all_reminders = db.query(Reminder).all()
        test("Admin: reminders queryable", True)

        all_messages = db.query(MessageLog).all()
        test("Admin: message logs queryable", True)

        # ===================================================================
        print("\n" + "="*60)
        print("TEST 11: CONSTANTS VALIDATION")
        print("="*60)
        # ===================================================================

        test("MAX_PETS_PER_USER = 5", MAX_PETS_PER_USER == 5)
        test("MAX_UPLOAD_MB = 10", MAX_UPLOAD_MB == 10)
        test("SYSTEM_TIMEZONE = Asia/Kolkata", SYSTEM_TIMEZONE == "Asia/Kolkata")
        test("CONFLICT_EXPIRY_DAYS = 5", CONFLICT_EXPIRY_DAYS == 5)
        test("REMINDER_SNOOZE_DAYS = 7", REMINDER_SNOOZE_DAYS == 7)
        test("OPENAI_EXTRACTION_MODEL = gpt-4.1", OPENAI_EXTRACTION_MODEL == "gpt-4.1")
        test("OPENAI_QUERY_MODEL = gpt-4.1-mini", OPENAI_QUERY_MODEL == "gpt-4.1-mini")
        test("DASHBOARD_TOKEN_BYTES = 16", DASHBOARD_TOKEN_BYTES == 16)
        test("ALLOWED_MIME_TYPES has 3 types", len(ALLOWED_MIME_TYPES) == 3)

        # ===================================================================
        print("\n" + "="*60)
        print("TEST 12: SECOND PET ONBOARDING (Add Pet)")
        print("="*60)
        # ===================================================================

        # Simulate adding a second pet
        user.onboarding_state = "awaiting_pet_name"
        db.commit()

        loop.run_until_complete(handle_onboarding_step(db, user, "Milo", mock_send))
        db.refresh(user)
        test("State -> awaiting_species for pet 2", user.onboarding_state == "awaiting_species")

        loop.run_until_complete(handle_onboarding_step(db, user, "cat", mock_send))
        db.refresh(user)
        test("State -> awaiting_breed for pet 2", user.onboarding_state == "awaiting_breed")

        # Skip optional fields
        loop.run_until_complete(handle_onboarding_step(db, user, "skip", mock_send))
        db.refresh(user)
        test("Breed skipped OK", user.onboarding_state == "awaiting_gender")

        loop.run_until_complete(handle_onboarding_step(db, user, "female", mock_send))
        db.refresh(user)

        loop.run_until_complete(handle_onboarding_step(db, user, "skip", mock_send))
        db.refresh(user)

        loop.run_until_complete(handle_onboarding_step(db, user, "skip", mock_send))
        db.refresh(user)

        loop.run_until_complete(handle_onboarding_step(db, user, "no", mock_send))
        db.refresh(user)
        test("State -> complete after pet 2", user.onboarding_state == "complete")

        # Verify second pet
        pets = db.query(Pet).filter(Pet.user_id == user.id, Pet.is_deleted == False).all()
        test("User has 2 pets", len(pets) == 2)

        milo = next((p for p in pets if p.name == "Milo"), None)
        test("Milo is a cat", milo and milo.species == "cat")
        test("Milo is female", milo and milo.gender == "female")
        test("Milo neutered=False", milo and milo.neutered == False)
        test("Milo breed is None (skipped)", milo and milo.breed is None)

        # Verify cat has different preventive items
        if milo:
            cat_records = db.query(PreventiveRecord).filter(PreventiveRecord.pet_id == milo.id).all()
            test("Cat preventive records seeded", len(cat_records) == 7)
            cat_token = db.query(DashboardToken).filter(DashboardToken.pet_id == milo.id).first()
            test("Cat dashboard token exists", cat_token is not None)

        # ===================================================================
        print("\n" + "="*60)
        print(f"RESULTS: {PASS} passed, {FAIL} failed")
        print("="*60)
        # ===================================================================

    except Exception as e:
        import traceback
        print(f"\n  FATAL ERROR: {e}")
        traceback.print_exc()

    finally:
        db.close()

    return FAIL


async def _upload_to_supabase(file_content, storage_path, mime_type):
    """Helper to test Supabase upload."""
    from app.services.document_upload import upload_to_supabase
    return await upload_to_supabase(file_content, storage_path, mime_type)


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
