"""
PetCircle Phase 1 — Reminder Response State Machine (Module 11)

Handles user responses to reminder WhatsApp interactive buttons.
Each response triggers a specific state transition on the reminder
and its linked preventive record.

Payload IDs (from constants — never hardcoded):
    - REMINDER_DONE: User confirms the preventive action was done today.
    - REMINDER_SNOOZE_7: User snoozes the reminder by 7 days.
    - REMINDER_RESCHEDULE: User wants to pick a new date.
    - REMINDER_CANCEL: User cancels this preventive item entirely.

State transitions:

    REMINDER_DONE:
        → preventive_record.last_done_date = today (IST)
        → Recalculate next_due_date and status from DB recurrence_days.
        → reminder.status = 'completed'

    REMINDER_SNOOZE_7:
        → preventive_record.next_due_date += 7 days
        → reminder.status = 'snoozed'
        → No recalculation — snooze is a manual override.

    REMINDER_RESCHEDULE:
        → Ask user for new date via WhatsApp text prompt.
        → On receiving valid date: update next_due_date, recalculate status.
        → Date validation uses parse_date from date_utils.

    REMINDER_CANCEL:
        → preventive_record.status = 'cancelled'
        → Cancelled records are excluded from future reminder runs.

Rules:
    - All payload IDs referenced from constants module.
    - All date operations in Asia/Kolkata timezone.
    - All transitions logged.
    - No silent overwrites — each transition is explicit.
"""

import logging
from datetime import date, timedelta
from uuid import UUID
from sqlalchemy.orm import Session
from app.models.reminder import Reminder
from app.models.preventive_record import PreventiveRecord
from app.models.preventive_master import PreventiveMaster
from app.core.constants import (
    REMINDER_DONE,
    REMINDER_SNOOZE_7,
    REMINDER_SNOOZE_DAYS,
    REMINDER_RESCHEDULE,
    REMINDER_CANCEL,
)
from app.services.preventive_calculator import (
    compute_next_due_date,
    compute_status,
)
from app.utils.date_utils import get_today_ist


logger = logging.getLogger(__name__)


# All valid reminder button payload IDs.
# Used for validation — reject unknown payloads immediately.
VALID_REMINDER_PAYLOADS = {
    REMINDER_DONE,
    REMINDER_SNOOZE_7,
    REMINDER_RESCHEDULE,
    REMINDER_CANCEL,
}


def handle_reminder_response(
    db: Session,
    reminder_id: UUID,
    payload: str,
) -> dict:
    """
    Process a user's response to a reminder WhatsApp button.

    Routes the response to the appropriate handler based on the
    button payload ID. Each handler implements a specific state
    transition on the reminder and its linked preventive record.

    Args:
        db: SQLAlchemy database session.
        reminder_id: UUID of the reminder being responded to.
        payload: The button payload ID (from WhatsApp interactive button).

    Returns:
        Dictionary with the result of the state transition:
            - status: result status string
            - reminder_id: the processed reminder ID
            - action: the payload that was processed
            - Additional fields depending on the action.

    Raises:
        ValueError: If the reminder is not found, already completed,
            or the payload is invalid.
    """
    # Validate the payload against known constants.
    # Reject unknown payloads to prevent unexpected behavior.
    if payload not in VALID_REMINDER_PAYLOADS:
        raise ValueError(
            f"Unknown reminder payload: '{payload}'. "
            f"Valid payloads: {VALID_REMINDER_PAYLOADS}"
        )

    # Load the reminder.
    reminder = (
        db.query(Reminder)
        .filter(Reminder.id == reminder_id)
        .first()
    )

    if not reminder:
        raise ValueError(f"Reminder not found: {reminder_id}")

    # Only 'sent' reminders can be responded to.
    # 'pending' reminders haven't been delivered yet.
    # 'completed' and 'snoozed' reminders are already processed.
    if reminder.status != "sent":
        raise ValueError(
            f"Reminder {reminder_id} cannot be responded to "
            f"(current status: {reminder.status}). "
            f"Only 'sent' reminders accept responses."
        )

    # Route to the appropriate handler.
    if payload == REMINDER_DONE:
        return _handle_done(db, reminder)
    elif payload == REMINDER_SNOOZE_7:
        return _handle_snooze(db, reminder)
    elif payload == REMINDER_RESCHEDULE:
        return _handle_reschedule_request(db, reminder)
    elif payload == REMINDER_CANCEL:
        return _handle_cancel(db, reminder)


def _handle_done(db: Session, reminder: Reminder) -> dict:
    """
    Handle REMINDER_DONE — user confirms the preventive action was done today.

    State transitions:
        - preventive_record.last_done_date = today (IST)
        - Recalculate next_due_date using recurrence_days from DB.
        - Recalculate status based on new next_due_date.
        - reminder.status = 'completed'

    Args:
        db: SQLAlchemy database session.
        reminder: The reminder being responded to.

    Returns:
        Result dictionary with updated fields.
    """
    # Load the linked preventive record.
    record = (
        db.query(PreventiveRecord)
        .filter(PreventiveRecord.id == reminder.preventive_record_id)
        .first()
    )

    if not record:
        raise ValueError(
            f"Preventive record not found for reminder: {reminder.id}"
        )

    # Load preventive master for recurrence_days — always from DB.
    master = (
        db.query(PreventiveMaster)
        .filter(PreventiveMaster.id == record.preventive_master_id)
        .first()
    )

    if not master:
        raise ValueError(
            f"Preventive master not found for record: {record.id}"
        )

    # Update last_done_date to today (IST).
    today = get_today_ist()
    record.last_done_date = today

    # Recalculate next_due_date from DB recurrence_days.
    # next_due_date = last_done_date + recurrence_days
    record.next_due_date = compute_next_due_date(today, master.recurrence_days)

    # Recalculate status based on new next_due_date.
    record.status = compute_status(record.next_due_date, master.reminder_before_days)

    # Mark reminder as completed.
    reminder.status = "completed"

    db.commit()

    logger.info(
        "Reminder DONE: reminder_id=%s, record_id=%s, "
        "last_done=%s, next_due=%s, new_status=%s",
        str(reminder.id),
        str(record.id),
        str(today),
        str(record.next_due_date),
        record.status,
    )

    return {
        "status": "completed",
        "reminder_id": str(reminder.id),
        "action": REMINDER_DONE,
        "last_done_date": str(today),
        "next_due_date": str(record.next_due_date),
        "record_status": record.status,
    }


def _handle_snooze(db: Session, reminder: Reminder) -> dict:
    """
    Handle REMINDER_SNOOZE_7 — user snoozes the reminder by 7 days.

    State transitions:
        - preventive_record.next_due_date += 7 days
        - reminder.status = 'snoozed'
        - No full recalculation — snooze is a manual override of the due date.
        - The record status is NOT recalculated because the user is
          intentionally delaying; we keep the current status until the
          next reminder engine run recalculates it.

    Args:
        db: SQLAlchemy database session.
        reminder: The reminder being responded to.

    Returns:
        Result dictionary with updated fields.
    """
    # Load the linked preventive record.
    record = (
        db.query(PreventiveRecord)
        .filter(PreventiveRecord.id == reminder.preventive_record_id)
        .first()
    )

    if not record:
        raise ValueError(
            f"Preventive record not found for reminder: {reminder.id}"
        )

    # Snooze: push next_due_date forward by REMINDER_SNOOZE_DAYS (from constants).
    # This is a manual override — not based on recurrence_days.
    old_due = record.next_due_date
    record.next_due_date = record.next_due_date + timedelta(days=REMINDER_SNOOZE_DAYS)

    # Mark reminder as snoozed.
    reminder.status = "snoozed"

    db.commit()

    logger.info(
        "Reminder SNOOZED: reminder_id=%s, record_id=%s, "
        "old_due=%s, new_due=%s",
        str(reminder.id),
        str(record.id),
        str(old_due),
        str(record.next_due_date),
    )

    return {
        "status": "snoozed",
        "reminder_id": str(reminder.id),
        "action": REMINDER_SNOOZE_7,
        "old_due_date": str(old_due),
        "new_due_date": str(record.next_due_date),
    }


def _handle_reschedule_request(db: Session, reminder: Reminder) -> dict:
    """
    Handle REMINDER_RESCHEDULE — user wants to pick a new date.

    This function does NOT complete the reschedule — it only marks
    the reminder as awaiting a date response. The actual date update
    happens in apply_reschedule_date() when the user sends a text
    message with the new date.

    The webhook layer detects that a reschedule is pending and routes
    the next text message to apply_reschedule_date().

    Args:
        db: SQLAlchemy database session.
        reminder: The reminder being responded to.

    Returns:
        Result dictionary indicating a date prompt should be sent.
    """
    logger.info(
        "Reminder RESCHEDULE requested: reminder_id=%s, record_id=%s. "
        "Awaiting user date input.",
        str(reminder.id),
        str(reminder.preventive_record_id),
    )

    # The reminder stays in 'sent' status until the user provides a date.
    # The service layer tracks this state and routes the next text message
    # to apply_reschedule_date().

    return {
        "status": "awaiting_date",
        "reminder_id": str(reminder.id),
        "action": REMINDER_RESCHEDULE,
        "message": "Please send the new date for this preventive item.",
    }


def apply_reschedule_date(
    db: Session,
    reminder_id: UUID,
    new_date: date,
) -> dict:
    """
    Apply a rescheduled date to a preventive record.

    Called when the user responds to a REMINDER_RESCHEDULE prompt with
    a valid date. The date must already be parsed and validated by
    the caller using parse_date() from date_utils.

    State transitions:
        - preventive_record.next_due_date = new_date
        - Recalculate preventive_record.status based on new next_due_date.
        - reminder.status = 'completed'

    Args:
        db: SQLAlchemy database session.
        reminder_id: UUID of the reminder being rescheduled.
        new_date: The validated new due date from user input.

    Returns:
        Result dictionary with updated fields.

    Raises:
        ValueError: If the reminder or its linked record is not found.
    """
    # Load the reminder.
    reminder = (
        db.query(Reminder)
        .filter(Reminder.id == reminder_id)
        .first()
    )

    if not reminder:
        raise ValueError(f"Reminder not found: {reminder_id}")

    # Load the linked preventive record.
    record = (
        db.query(PreventiveRecord)
        .filter(PreventiveRecord.id == reminder.preventive_record_id)
        .first()
    )

    if not record:
        raise ValueError(
            f"Preventive record not found for reminder: {reminder_id}"
        )

    # Load preventive master for reminder_before_days (status calculation).
    master = (
        db.query(PreventiveMaster)
        .filter(PreventiveMaster.id == record.preventive_master_id)
        .first()
    )

    if not master:
        raise ValueError(
            f"Preventive master not found for record: {record.id}"
        )

    # Update next_due_date to the user-provided date.
    old_due = record.next_due_date
    record.next_due_date = new_date

    # Recalculate status based on the new next_due_date.
    record.status = compute_status(new_date, master.reminder_before_days)

    # Mark reminder as completed — reschedule is done.
    reminder.status = "completed"

    db.commit()

    logger.info(
        "Reminder RESCHEDULED: reminder_id=%s, record_id=%s, "
        "old_due=%s, new_due=%s, new_status=%s",
        str(reminder.id),
        str(record.id),
        str(old_due),
        str(new_date),
        record.status,
    )

    return {
        "status": "rescheduled",
        "reminder_id": str(reminder.id),
        "action": REMINDER_RESCHEDULE,
        "old_due_date": str(old_due),
        "new_due_date": str(new_date),
        "record_status": record.status,
    }


def _handle_cancel(db: Session, reminder: Reminder) -> dict:
    """
    Handle REMINDER_CANCEL — user cancels this preventive item.

    State transitions:
        - preventive_record.status = 'cancelled'
        - reminder.status = 'completed'
        - Cancelled records are excluded from future reminder engine runs.
        - Cancellation is permanent for this record — a new record must be
          created if the user wants to resume tracking.

    Args:
        db: SQLAlchemy database session.
        reminder: The reminder being responded to.

    Returns:
        Result dictionary confirming cancellation.
    """
    # Load the linked preventive record.
    record = (
        db.query(PreventiveRecord)
        .filter(PreventiveRecord.id == reminder.preventive_record_id)
        .first()
    )

    if not record:
        raise ValueError(
            f"Preventive record not found for reminder: {reminder.id}"
        )

    # Cancel the preventive record.
    # Cancelled records are excluded from the reminder engine queries
    # (it only processes 'upcoming' and 'overdue' records).
    record.status = "cancelled"

    # Mark reminder as completed — cancel is a terminal action.
    reminder.status = "completed"

    db.commit()

    logger.info(
        "Reminder CANCELLED: reminder_id=%s, record_id=%s, pet_id=%s",
        str(reminder.id),
        str(record.id),
        str(record.pet_id),
    )

    return {
        "status": "cancelled",
        "reminder_id": str(reminder.id),
        "action": REMINDER_CANCEL,
        "record_id": str(record.id),
    }
