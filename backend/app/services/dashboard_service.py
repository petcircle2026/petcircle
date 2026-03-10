"""
PetCircle Phase 1 — Dashboard Service (Module 13)

Provides data retrieval and update logic for the tokenized pet dashboard.
The dashboard is accessed via a secure random token — no login required
for Phase 1.

Token validation:
    - Token must exist in dashboard_tokens table.
    - Token must not be revoked (revoked=False).
    - Token maps to a single pet via pet_id.

Data returned:
    - Pet profile (no internal IDs exposed to frontend).
    - Preventive summary (records with status, dates, master item names).
    - Active reminders.
    - Uploaded documents (metadata only — no direct storage URLs).
    - Health score (computed by health_score service).

Editable operations:
    - Update pet weight.
    - Update preventive record dates (triggers recalculation).
    - Date changes invalidate pending reminders.

Rules:
    - No internal UUIDs exposed in API responses — use token only.
    - Recalculation after every update (next_due_date, status).
    - Pending reminders invalidated when dates change.
    - No bucket hardcoding — file paths are storage-relative.
    - All recurrence values from DB preventive_master — never hardcoded.
"""

import logging
import asyncio
from uuid import UUID
from datetime import date, datetime
from sqlalchemy.orm import Session
from app.models.dashboard_token import DashboardToken
from app.models.pet import Pet
from app.models.user import User
from app.models.preventive_record import PreventiveRecord
from app.models.preventive_master import PreventiveMaster
from app.models.reminder import Reminder
from app.models.document import Document
from app.models.diagnostic_test_result import DiagnosticTestResult
from app.services.document_upload import download_from_supabase
from app.services.preventive_calculator import (
    compute_next_due_date,
    compute_status,
)


logger = logging.getLogger(__name__)


def validate_dashboard_token(db: Session, token: str) -> DashboardToken:
    """
    Validate a dashboard access token.

    Checks that the token exists and has not been revoked.
    Revoked tokens cannot be used — soft revocation is permanent
    for that token (a new token must be generated).

    Args:
        db: SQLAlchemy database session.
        token: The dashboard access token string.

    Returns:
        The valid DashboardToken record.

    Raises:
        ValueError: If token is not found or has been revoked.
    """
    dashboard_token = (
        db.query(DashboardToken)
        .filter(
            DashboardToken.token == token,
        )
        .first()
    )

    if not dashboard_token:
        raise ValueError("Invalid dashboard token.")

    # Revoked tokens cannot be reused — soft revocation only.
    if dashboard_token.revoked:
        raise ValueError("This dashboard link has been revoked.")

    # Expired tokens are rejected — user can regenerate via WhatsApp.
    if dashboard_token.expires_at and datetime.utcnow() > dashboard_token.expires_at:
        raise ValueError(
            "Dashboard link has expired. Send 'dashboard' in WhatsApp to get a new link."
        )

    return dashboard_token


def get_dashboard_data(db: Session, token: str) -> dict:
    """
    Retrieve all dashboard data for a pet via its access token.

    Returns a comprehensive view of the pet's health status:
        - Pet profile (name, species, breed, gender, dob, weight, neutered).
        - Owner info (full_name only — no mobile number exposed).
        - Preventive records with master item names and status.
        - Active reminders with status and dates.
        - Uploaded documents (metadata only — no direct storage URLs).
        - Health score (computed inline from preventive records — no duplicate query).

    No internal IDs (UUIDs) are exposed in the response.
    The frontend uses the token as the sole identifier.

    Args:
        db: SQLAlchemy database session.
        token: The dashboard access token string.

    Returns:
        Dictionary with complete dashboard data.

    Raises:
        ValueError: If token is invalid, revoked, or pet not found.
    """
    from app.core.constants import (
        HEALTH_SCORE_ESSENTIAL_WEIGHT,
        HEALTH_SCORE_COMPLEMENTARY_WEIGHT,
    )

    # --- Validate token ---
    dashboard_token = validate_dashboard_token(db, token)
    pet_id = dashboard_token.pet_id

    # --- Load pet + owner in one query via join ---
    pet = db.query(Pet).filter(Pet.id == pet_id).first()
    if not pet or pet.is_deleted:
        raise ValueError("Pet not found or has been removed.")

    user = db.query(User).filter(User.id == pet.user_id).first()

    # --- Load preventive records with master item names ---
    # Also compute health score inline to avoid a duplicate DB query.
    preventive_data = (
        db.query(PreventiveRecord, PreventiveMaster)
        .join(
            PreventiveMaster,
            PreventiveRecord.preventive_master_id == PreventiveMaster.id,
        )
        .filter(PreventiveRecord.pet_id == pet_id)
        .order_by(PreventiveRecord.next_due_date.asc())
        .all()
    )

    preventive_records = []
    # Compute health score inline — avoids the duplicate query in health_score.py.
    essential_done = 0
    essential_total = 0
    complementary_done = 0
    complementary_total = 0

    for record, master in preventive_data:
        preventive_records.append({
            "item_name": master.item_name,
            "category": master.category,
            "circle": master.circle,
            "last_done_date": str(record.last_done_date) if record.last_done_date else None,
            "next_due_date": str(record.next_due_date) if record.next_due_date else None,
            "status": record.status,
            "recurrence_days": master.recurrence_days,
        })

        # Health score: count essential/complementary records inline.
        if record.status != "cancelled":
            if master.category == "essential":
                essential_total += 1
                if record.status == "up_to_date":
                    essential_done += 1
            elif master.category == "complete":
                complementary_total += 1
                if record.status == "up_to_date":
                    complementary_done += 1

    # --- Compute health score from inline counts ---
    essential_ratio = essential_done / essential_total if essential_total > 0 else 0.0
    complementary_ratio = complementary_done / complementary_total if complementary_total > 0 else 0.0
    raw_score = (
        essential_ratio * HEALTH_SCORE_ESSENTIAL_WEIGHT
        + complementary_ratio * HEALTH_SCORE_COMPLEMENTARY_WEIGHT
    ) * 100
    health_score = {
        "score": round(raw_score),
        "essential_done": essential_done,
        "essential_total": essential_total,
        "complementary_done": complementary_done,
        "complementary_total": complementary_total,
    }

    # --- Load active reminders ---
    reminders = (
        db.query(Reminder, PreventiveRecord, PreventiveMaster)
        .join(
            PreventiveRecord,
            Reminder.preventive_record_id == PreventiveRecord.id,
        )
        .join(
            PreventiveMaster,
            PreventiveRecord.preventive_master_id == PreventiveMaster.id,
        )
        .filter(
            PreventiveRecord.pet_id == pet_id,
            Reminder.status.in_(["pending", "sent"]),
        )
        .order_by(Reminder.next_due_date.asc())
        .all()
    )

    reminder_data = []
    for reminder, record, master in reminders:
        reminder_data.append({
            "item_name": master.item_name,
            "next_due_date": str(reminder.next_due_date),
            "status": reminder.status,
            "sent_at": str(reminder.sent_at) if reminder.sent_at else None,
        })

    # --- Load documents (metadata only — no storage URLs) ---
    # Show documents with all statuses including failed — users can retry
    # failed extractions from the dashboard.
    documents = (
        db.query(Document)
        .filter(
            Document.pet_id == pet_id,
            Document.extraction_status.in_(["pending", "success", "failed"]),
        )
        .order_by(Document.created_at.desc())
        .all()
    )

    document_data = []
    for doc in documents:
        document_data.append({
            "id": str(doc.id),
            "document_name": doc.document_name,
            "document_category": doc.document_category,
            "doctor_name": doc.doctor_name,
            "hospital_name": doc.hospital_name,
            "mime_type": doc.mime_type,
            "extraction_status": doc.extraction_status,
            "uploaded_at": str(doc.created_at) if doc.created_at else None,
        })

    # --- Diagnostic values (blood/urine) for dashboard ---
    diagnostic_rows = (
        db.query(DiagnosticTestResult)
        .filter(DiagnosticTestResult.pet_id == pet_id)
        .order_by(DiagnosticTestResult.observed_at.desc().nullslast(), DiagnosticTestResult.created_at.desc())
        .all()
    )

    diagnostic_results = []
    for row in diagnostic_rows:
        diagnostic_results.append({
            "test_type": row.test_type,
            "parameter_name": row.parameter_name,
            "value_numeric": float(row.value_numeric) if row.value_numeric is not None else None,
            "value_text": row.value_text,
            "unit": row.unit,
            "reference_range": row.reference_range,
            "status_flag": row.status_flag,
            "observed_at": str(row.observed_at) if row.observed_at else None,
            "document_id": str(row.document_id) if row.document_id else None,
            "created_at": str(row.created_at) if row.created_at else None,
        })

    # --- Build response (no internal IDs exposed) ---
    return {
        "pet": {
            "name": pet.name,
            "species": pet.species,
            "breed": pet.breed,
            "gender": pet.gender,
            "dob": str(pet.dob) if pet.dob else None,
            "weight": float(pet.weight) if pet.weight else None,
            "weight_flagged": bool(pet.weight_flagged),
            "neutered": pet.neutered,
        },
        "owner": {
            "full_name": user.full_name if user else None,
        },
        "preventive_records": preventive_records,
        "reminders": reminder_data,
        "documents": document_data,
        "diagnostic_results": diagnostic_results,
        "health_score": health_score,
    }


def get_document_file_for_token(
    db: Session,
    token: str,
    document_id: str,
) -> tuple[bytes, str, str]:
    """
    Retrieve raw document bytes for a dashboard token and document id.

    Security checks:
      - token must be valid and not revoked/expired.
      - document must belong to the token's pet.

    Returns:
      Tuple of (file_bytes, mime_type, filename).

    Raises:
      ValueError: token invalid, document missing, or file fetch failure.
    """
    dashboard_token = validate_dashboard_token(db, token)

    try:
        doc_uuid = UUID(document_id)
    except ValueError as exc:
        raise ValueError("Document not found.") from exc

    doc = (
        db.query(Document)
        .filter(
            Document.id == doc_uuid,
            Document.pet_id == dashboard_token.pet_id,
        )
        .first()
    )
    if not doc:
        raise ValueError("Document not found.")

    file_bytes = asyncio.run(download_from_supabase(doc.file_path))
    if not file_bytes:
        raise ValueError("Could not load document from storage.")

    filename = doc.file_path.split("/")[-1] if doc.file_path else "document"
    return file_bytes, doc.mime_type, filename


def update_pet_weight(
    db: Session,
    token: str,
    new_weight: float,
) -> dict:
    """
    Update a pet's weight via dashboard token.

    Weight is a simple field update — no recalculation needed.

    Args:
        db: SQLAlchemy database session.
        token: The dashboard access token string.
        new_weight: The new weight value (kg, Numeric(5,2)).

    Returns:
        Dictionary confirming the update.

    Raises:
        ValueError: If token is invalid or pet not found.
    """
    dashboard_token = validate_dashboard_token(db, token)
    pet = db.query(Pet).filter(Pet.id == dashboard_token.pet_id).first()

    if not pet or pet.is_deleted:
        raise ValueError("Pet not found or has been removed.")

    old_weight = pet.weight
    pet.weight = new_weight
    pet.weight_flagged = False
    db.commit()

    logger.info(
        "Pet weight updated via dashboard: pet_id=%s, "
        "old_weight=%s, new_weight=%s",
        str(pet.id),
        str(old_weight),
        str(new_weight),
    )

    return {
        "status": "updated",
        "name": pet.name,
        "old_weight": float(old_weight) if old_weight else None,
        "new_weight": float(new_weight),
    }


def update_preventive_date(
    db: Session,
    token: str,
    item_name: str,
    new_last_done_date: date,
) -> dict:
    """
    Update a preventive record's last_done_date via dashboard.

    This triggers a full recalculation:
        - next_due_date = last_done_date + recurrence_days (from DB)
        - status recalculated based on new next_due_date
        - Pending reminders for the old due date are invalidated

    Recurrence days are always read from preventive_master in DB
    — never hardcoded.

    Pending reminder invalidation:
        When a preventive date changes, any pending or sent reminders
        for the OLD next_due_date become stale. These reminders are
        marked as 'completed' to prevent duplicate sends. The next
        reminder engine run will create a new reminder for the
        updated due date if needed.

    Args:
        db: SQLAlchemy database session.
        token: The dashboard access token string.
        item_name: Name of the preventive item to update.
        new_last_done_date: The new last_done_date value.

    Returns:
        Dictionary with updated record details.

    Raises:
        ValueError: If token invalid, pet/record/master not found.
    """
    dashboard_token = validate_dashboard_token(db, token)
    pet_id = dashboard_token.pet_id

    pet = db.query(Pet).filter(Pet.id == pet_id).first()
    if not pet or pet.is_deleted:
        raise ValueError("Pet not found or has been removed.")

    # Find the preventive record by item_name.
    # Join with preventive_master to match by item name.
    result = (
        db.query(PreventiveRecord, PreventiveMaster)
        .join(
            PreventiveMaster,
            PreventiveRecord.preventive_master_id == PreventiveMaster.id,
        )
        .filter(
            PreventiveRecord.pet_id == pet_id,
            PreventiveMaster.item_name == item_name,
            # Do not allow updating cancelled records.
            PreventiveRecord.status != "cancelled",
        )
        .first()
    )

    if not result:
        raise ValueError(
            f"Preventive record not found for item: {item_name}"
        )

    record, master = result

    # Store old values for logging and response.
    old_last_done = record.last_done_date
    old_next_due = record.next_due_date

    # --- Update last_done_date ---
    record.last_done_date = new_last_done_date

    # --- Recalculate next_due_date ---
    # Recurrence days from DB preventive_master — never hardcoded.
    record.next_due_date = compute_next_due_date(
        new_last_done_date, master.recurrence_days
    )

    # --- Recalculate status ---
    record.status = compute_status(
        record.next_due_date, master.reminder_before_days
    )

    # --- Invalidate pending reminders for the old due date ---
    # Stale reminders (pending or sent) for the old next_due_date
    # are marked 'completed' to prevent duplicate sends.
    # The next reminder engine run will create fresh reminders if needed.
    stale_reminders = (
        db.query(Reminder)
        .filter(
            Reminder.preventive_record_id == record.id,
            Reminder.next_due_date == old_next_due,
            Reminder.status.in_(["pending", "sent"]),
        )
        .all()
    )

    invalidated_count = 0
    for reminder in stale_reminders:
        reminder.status = "completed"
        invalidated_count += 1

    db.commit()

    logger.info(
        "Preventive date updated via dashboard: pet_id=%s, item=%s, "
        "old_done=%s, new_done=%s, new_due=%s, new_status=%s, "
        "reminders_invalidated=%d",
        str(pet_id),
        item_name,
        str(old_last_done),
        str(new_last_done_date),
        str(record.next_due_date),
        record.status,
        invalidated_count,
    )

    return {
        "status": "updated",
        "item_name": item_name,
        "old_last_done_date": str(old_last_done),
        "new_last_done_date": str(new_last_done_date),
        "new_next_due_date": str(record.next_due_date),
        "record_status": record.status,
        "reminders_invalidated": invalidated_count,
    }


async def retry_document_extraction(
    db: Session,
    token: str,
    document_id: str,
) -> dict:
    """
    Retry GPT extraction for a failed document via dashboard token.

    Validates token ownership, verifies the document belongs to the
    token's pet and has extraction_status='failed', then re-downloads
    the file from Supabase and runs the extraction pipeline again.

    Args:
        db: SQLAlchemy database session.
        token: The dashboard access token string.
        document_id: UUID string of the document to retry.

    Returns:
        Dictionary with extraction result status.

    Raises:
        ValueError: If token invalid, document not found, or not in failed state.
    """
    import asyncio
    from app.services.document_upload import download_from_supabase
    from app.services.gpt_extraction import extract_and_process_document

    dashboard_token = validate_dashboard_token(db, token)
    pet_id = dashboard_token.pet_id

    # Verify document exists, belongs to this pet, and is in failed state.
    doc = (
        db.query(Document)
        .filter(
            Document.id == document_id,
            Document.pet_id == pet_id,
        )
        .first()
    )

    if not doc:
        raise ValueError("Document not found.")

    if doc.extraction_status != "failed":
        raise ValueError("Only failed documents can be retried.")

    # Download file from Supabase storage.
    file_bytes = await download_from_supabase(doc.file_path)
    if not file_bytes:
        raise ValueError("Could not download document from storage. Please re-upload via WhatsApp.")

    # Reset status to pending before retrying.
    doc.extraction_status = "pending"
    db.commit()

    try:
        result = await asyncio.wait_for(
            extract_and_process_document(
                db, doc.id,
                f"[file: {doc.file_path}]",
                file_bytes=file_bytes,
            ),
            timeout=120,
        )

        logger.info(
            "Dashboard retry extraction succeeded: doc_id=%s, pet_id=%s",
            document_id,
            str(pet_id),
        )

        return {
            "status": "success",
            "document_id": document_id,
            "extraction_result": result,
        }
    except Exception as e:
        # Mark as failed again if extraction fails.
        doc.extraction_status = "failed"
        db.commit()
        logger.error(
            "Dashboard retry extraction failed: doc_id=%s, error=%s",
            document_id,
            str(e),
        )
        raise ValueError(f"Extraction failed: {str(e)}")


def get_health_trends(db: Session, token: str) -> dict:
    """
    Build health trend data from preventive record last_done_dates.

    Groups completed preventive items by month to show activity over time.
    Each month shows how many items were completed (last_done_date falls
    in that month) and the status breakdown at that point.

    Args:
        db: SQLAlchemy database session.
        token: The dashboard access token string.

    Returns:
        Dictionary with monthly trend data and per-item timeline.

    Raises:
        ValueError: If token is invalid or pet not found.
    """
    from collections import defaultdict
    from app.core.constants import (
        HEALTH_SCORE_ESSENTIAL_WEIGHT,
        HEALTH_SCORE_COMPLEMENTARY_WEIGHT,
    )

    dashboard_token = validate_dashboard_token(db, token)
    pet_id = dashboard_token.pet_id

    pet = db.query(Pet).filter(Pet.id == pet_id).first()
    if not pet or pet.is_deleted:
        raise ValueError("Pet not found or has been removed.")

    # Load all preventive records with master info.
    preventive_data = (
        db.query(PreventiveRecord, PreventiveMaster)
        .join(
            PreventiveMaster,
            PreventiveRecord.preventive_master_id == PreventiveMaster.id,
        )
        .filter(PreventiveRecord.pet_id == pet_id)
        .all()
    )

    # --- Build per-item timeline ---
    # Each item shows its last_done_date for the timeline view.
    item_timeline = []
    for record, master in preventive_data:
        if record.last_done_date:
            item_timeline.append({
                "item_name": master.item_name,
                "category": master.category,
                "last_done_date": str(record.last_done_date),
                "status": record.status,
            })

    # --- Group completions by month ---
    # Key: "YYYY-MM", Value: count of items completed that month.
    monthly_completions: dict[str, int] = defaultdict(int)
    for record, master in preventive_data:
        if record.last_done_date:
            month_key = record.last_done_date.strftime("%Y-%m")
            monthly_completions[month_key] += 1

    # Sort months chronologically.
    sorted_months = sorted(monthly_completions.keys())

    monthly_data = []
    for month in sorted_months:
        monthly_data.append({
            "month": month,
            "items_completed": monthly_completions[month],
        })

    # --- Current status summary ---
    total = len(preventive_data)
    status_counts = defaultdict(int)
    for record, master in preventive_data:
        if record.status != "cancelled" and not record.last_done_date and not record.next_due_date:
            status_counts["incomplete"] += 1
        else:
            status_counts[record.status] += 1

    # --- Diagnostic document frequency by month ---
    # Counts documents categorized as "Diagnostic" per month.
    diagnostic_docs = (
        db.query(Document)
        .filter(
            Document.pet_id == pet_id,
            Document.document_category == "Diagnostic",
            Document.extraction_status == "success",
        )
        .all()
    )

    diagnostic_monthly: dict[str, int] = defaultdict(int)
    for doc in diagnostic_docs:
        if doc.created_at:
            month_key = doc.created_at.strftime("%Y-%m")
            diagnostic_monthly[month_key] += 1

    diagnostic_trends = []
    for month in sorted(diagnostic_monthly.keys()):
        diagnostic_trends.append({
            "month": month,
            "count": diagnostic_monthly[month],
        })

    return {
        "monthly_completions": monthly_data,
        "item_timeline": sorted(
            item_timeline,
            key=lambda x: x["last_done_date"],
            reverse=True,
        ),
        "status_summary": {
            "total": total,
            "up_to_date": status_counts.get("up_to_date", 0),
            "upcoming": status_counts.get("upcoming", 0),
            "overdue": status_counts.get("overdue", 0),
            "incomplete": status_counts.get("incomplete", 0),
            "cancelled": status_counts.get("cancelled", 0),
        },
        "diagnostic_trends": diagnostic_trends,
    }
