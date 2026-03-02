"""
PetCircle Phase 1 — Conflict Detection Engine (Module 8)

Detects and manages date conflicts when a newly extracted preventive date
differs from the existing latest date on a preventive record.

Conflict lifecycle:
    1. New date extracted (from GPT or manual entry).
    2. Compare with existing latest record for (pet_id, preventive_master_id).
    3. If dates differ → insert conflict_flags row (status='pending').
    4. User resolves via WhatsApp interactive buttons:
        - CONFLICT_USE_NEW: update last_done_date to new_date, recalculate.
        - CONFLICT_KEEP_EXISTING: discard new_date, keep current record.
    5. If unresolved after 5 days → auto-resolve as KEEP_EXISTING (Module 19).

Rules:
    - No overwrite allowed — conflicts must be explicitly resolved.
    - No partial merge — it's all-or-nothing.
    - Conflict expiry: 5 days, auto-resolve KEEP_EXISTING, log action.
    - Button payload IDs from constants — never hardcoded.
"""

import logging
from datetime import date
from uuid import UUID
from sqlalchemy.orm import Session
from app.models.preventive_record import PreventiveRecord
from app.models.conflict_flag import ConflictFlag
from app.core.constants import CONFLICT_USE_NEW, CONFLICT_KEEP_EXISTING
from app.services.preventive_calculator import calculate_and_update_record


logger = logging.getLogger(__name__)


def check_and_create_conflict(
    db: Session,
    pet_id: UUID,
    preventive_master_id: UUID,
    new_date: date,
) -> ConflictFlag | None:
    """
    Check if a newly extracted date conflicts with the existing record.

    A conflict exists when:
        1. A preventive record already exists for (pet_id, preventive_master_id).
        2. The new_date differs from the existing record's last_done_date.

    If a conflict is detected:
        - A conflict_flags row is created with status='pending'.
        - The caller should send the petcircle_conflict_v1 WhatsApp template.

    If no conflict:
        - Returns None — the caller proceeds with normal record creation.

    This function does NOT overwrite any existing data. The conflict must
    be resolved explicitly by the user or by auto-expiry (Module 19).

    Args:
        db: SQLAlchemy database session.
        pet_id: UUID of the pet.
        preventive_master_id: UUID of the preventive master item.
        new_date: The newly extracted date that may conflict.

    Returns:
        ConflictFlag if a conflict was created, None if no conflict exists.
    """
    # Find the latest existing record for this pet + preventive item.
    # Order by last_done_date descending to get the most recent one.
    existing_record = (
        db.query(PreventiveRecord)
        .filter(
            PreventiveRecord.pet_id == pet_id,
            PreventiveRecord.preventive_master_id == preventive_master_id,
        )
        .order_by(PreventiveRecord.last_done_date.desc())
        .first()
    )

    if not existing_record:
        # No existing record — no conflict possible.
        # Caller should proceed with creating a new preventive record.
        return None

    if existing_record.last_done_date == new_date:
        # Dates match — no conflict. This is an idempotent re-extraction.
        logger.info(
            "No conflict: dates match for pet_id=%s, item=%s, date=%s",
            str(pet_id),
            str(preventive_master_id),
            str(new_date),
        )
        return None

    # Check if there is already a pending conflict for this record.
    # Prevents duplicate conflict flags for the same record.
    existing_conflict = (
        db.query(ConflictFlag)
        .filter(
            ConflictFlag.preventive_record_id == existing_record.id,
            ConflictFlag.status == "pending",
        )
        .first()
    )

    if existing_conflict:
        logger.info(
            "Pending conflict already exists for record_id=%s. "
            "Updating new_date from %s to %s.",
            str(existing_record.id),
            str(existing_conflict.new_date),
            str(new_date),
        )
        # Update the existing conflict with the latest extracted date.
        existing_conflict.new_date = new_date
        db.commit()
        return existing_conflict

    # Dates differ — create a conflict flag.
    # Status is 'pending' until user resolves via WhatsApp buttons
    # or auto-expiry resolves it after CONFLICT_EXPIRY_DAYS.
    conflict = ConflictFlag(
        preventive_record_id=existing_record.id,
        new_date=new_date,
        status="pending",
    )

    db.add(conflict)
    db.commit()

    logger.info(
        "Conflict detected: record_id=%s, existing_date=%s, new_date=%s",
        str(existing_record.id),
        str(existing_record.last_done_date),
        str(new_date),
    )

    return conflict


def resolve_conflict(
    db: Session,
    conflict_id: UUID,
    resolution: str,
) -> ConflictFlag:
    """
    Resolve a pending conflict based on user's decision.

    Resolution options (from WhatsApp button payload IDs):
        - CONFLICT_USE_NEW: Replace last_done_date with new_date,
          recalculate next_due_date and status.
        - CONFLICT_KEEP_EXISTING: Discard the new_date, keep
          the current record unchanged.

    No partial merge is allowed — the resolution is all-or-nothing.

    Args:
        db: SQLAlchemy database session.
        conflict_id: UUID of the conflict_flags row to resolve.
        resolution: One of CONFLICT_USE_NEW or CONFLICT_KEEP_EXISTING
            (from constants — never hardcoded).

    Returns:
        The updated ConflictFlag object.

    Raises:
        ValueError: If the conflict is not found or not in 'pending' status.
        ValueError: If the resolution value is invalid.
    """
    # Validate the resolution value against known constants.
    # Button payload IDs are defined in constants — never hardcoded here.
    valid_resolutions = {CONFLICT_USE_NEW, CONFLICT_KEEP_EXISTING}
    if resolution not in valid_resolutions:
        raise ValueError(
            f"Invalid conflict resolution: '{resolution}'. "
            f"Must be one of: {valid_resolutions}"
        )

    # Load the conflict flag.
    conflict = (
        db.query(ConflictFlag)
        .filter(ConflictFlag.id == conflict_id)
        .first()
    )

    if not conflict:
        raise ValueError(f"Conflict not found: {conflict_id}")

    if conflict.status != "pending":
        raise ValueError(
            f"Conflict {conflict_id} is already resolved (status={conflict.status})."
        )

    # Load the linked preventive record.
    record = (
        db.query(PreventiveRecord)
        .filter(PreventiveRecord.id == conflict.preventive_record_id)
        .first()
    )

    if not record:
        raise ValueError(
            f"Preventive record not found for conflict: {conflict_id}"
        )

    if resolution == CONFLICT_USE_NEW:
        # User chose to use the new date — update the record.
        # Replace last_done_date and recalculate next_due_date + status.
        record.last_done_date = conflict.new_date
        conflict.status = "resolved"
        db.commit()

        # Recalculate next_due_date and status from DB recurrence_days.
        calculate_and_update_record(db, record.id)

        logger.info(
            "Conflict resolved USE_NEW: conflict_id=%s, "
            "record_id=%s, new_date=%s",
            str(conflict_id),
            str(record.id),
            str(conflict.new_date),
        )

    elif resolution == CONFLICT_KEEP_EXISTING:
        # User chose to keep existing date — discard the new_date.
        # No changes to the preventive record.
        conflict.status = "resolved"
        db.commit()

        logger.info(
            "Conflict resolved KEEP_EXISTING: conflict_id=%s, "
            "record_id=%s, discarded_date=%s",
            str(conflict_id),
            str(record.id),
            str(conflict.new_date),
        )

    return conflict
