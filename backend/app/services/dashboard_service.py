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
from app.services.health_score import compute_health_score
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
        - Uploaded documents (metadata only — no storage URLs).
        - Health score (computed from preventive records).

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
    # --- Validate token ---
    dashboard_token = validate_dashboard_token(db, token)
    pet_id = dashboard_token.pet_id

    # --- Load pet ---
    pet = db.query(Pet).filter(Pet.id == pet_id).first()
    if not pet or pet.is_deleted:
        raise ValueError("Pet not found or has been removed.")

    # --- Load owner (limited info) ---
    user = db.query(User).filter(User.id == pet.user_id).first()

    # --- Load preventive records with master item names ---
    # Recurrence and config always from preventive_master in DB.
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
    for record, master in preventive_data:
        preventive_records.append({
            "item_name": master.item_name,
            "category": master.category,
            "last_done_date": str(record.last_done_date) if record.last_done_date else None,
            "next_due_date": str(record.next_due_date) if record.next_due_date else None,
            "status": record.status,
            "recurrence_days": master.recurrence_days,
        })

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
    documents = (
        db.query(Document)
        .filter(Document.pet_id == pet_id)
        .order_by(Document.created_at.desc())
        .all()
    )

    document_data = []
    for doc in documents:
        document_data.append({
            "mime_type": doc.mime_type,
            "extraction_status": doc.extraction_status,
            "uploaded_at": str(doc.created_at) if doc.created_at else None,
        })

    # --- Compute health score ---
    health_score = compute_health_score(db, pet_id)

    # --- Build response (no internal IDs exposed) ---
    return {
        "pet": {
            "name": pet.name,
            "species": pet.species,
            "breed": pet.breed,
            "gender": pet.gender,
            "dob": str(pet.dob) if pet.dob else None,
            "weight": float(pet.weight) if pet.weight else None,
            "neutered": pet.neutered,
        },
        "owner": {
            "full_name": user.full_name if user else None,
        },
        "preventive_records": preventive_records,
        "reminders": reminder_data,
        "documents": document_data,
        "health_score": health_score,
    }


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
