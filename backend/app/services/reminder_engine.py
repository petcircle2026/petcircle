"""
PetCircle Phase 1 — Reminder Engine (Module 10)

Stateless daily reminder processor. Designed to run as a Render cron
job at 8 AM IST.

Route: /internal/run-reminder-engine

Processing steps:
    1. Find all preventive_records with status 'upcoming' or 'overdue'.
    2. For each record, check if a reminder already exists for this
       (preventive_record_id, next_due_date) — deduplication via UNIQUE constraint.
    3. If no reminder exists, insert one with status='pending'.
    4. Send the appropriate WhatsApp template message (reminder or overdue).
    5. Update reminder.status to 'sent' and set sent_at timestamp.

Rules:
    - Stateless execution — safe to re-run multiple times without side effects.
    - Deduplication enforced by UNIQUE(preventive_record_id, next_due_date).
    - WhatsApp retry: once only (via retry_whatsapp_call).
    - Rate limiting: max 20 messages/min per number (rolling window).
    - Logging mandatory for every action.
    - Never crashes on WhatsApp failure — continues to next record.
    - Template names loaded from environment config — never hardcoded.
"""

import asyncio
import logging
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.models.preventive_record import PreventiveRecord
from app.models.preventive_master import PreventiveMaster
from app.models.reminder import Reminder
from app.models.pet import Pet
from app.models.user import User
from app.utils.date_utils import get_today_ist, IST


logger = logging.getLogger(__name__)


def run_reminder_engine(db: Session) -> dict:
    """
    Execute the daily reminder engine — find due records and create reminders.

    This function is the core of the reminder system. It runs statelessly
    and can be safely called multiple times (idempotent via UNIQUE constraint).

    Processing logic:
        1. Query all preventive records with status 'upcoming' or 'overdue'.
        2. Skip records belonging to soft-deleted pets or users.
        3. For each qualifying record, attempt to insert a reminder.
        4. The UNIQUE(preventive_record_id, next_due_date) constraint
           prevents duplicate reminders — IntegrityError is caught silently.
        5. Track results for logging and admin visibility.

    WhatsApp message sending is handled separately in send_pending_reminders()
    to keep the creation and sending phases distinct.

    Args:
        db: SQLAlchemy database session.

    Returns:
        Dictionary with processing results:
            - records_checked: total records examined
            - reminders_created: new reminders inserted
            - reminders_skipped: duplicates prevented by UNIQUE constraint
            - errors: number of unexpected errors
    """
    today = get_today_ist()

    results = {
        "records_checked": 0,
        "reminders_created": 0,
        "reminders_skipped": 0,
        "errors": 0,
    }

    # Find all preventive records that are 'upcoming' or 'overdue'.
    # These are the records that need reminders.
    records = (
        db.query(PreventiveRecord)
        .filter(
            PreventiveRecord.status.in_(["upcoming", "overdue"]),
        )
        .all()
    )

    for record in records:
        results["records_checked"] += 1

        # --- Skip records for soft-deleted pets ---
        # Soft-deleted pets should not receive reminders.
        pet = db.query(Pet).filter(Pet.id == record.pet_id).first()
        if not pet or pet.is_deleted:
            logger.info(
                "Skipping reminder for deleted pet: record_id=%s, pet_id=%s",
                str(record.id),
                str(record.pet_id),
            )
            continue

        # --- Skip records for soft-deleted users ---
        # Soft-deleted users should not receive reminders.
        user = db.query(User).filter(User.id == pet.user_id).first()
        if not user or user.is_deleted:
            logger.info(
                "Skipping reminder for deleted user: record_id=%s, user_id=%s",
                str(record.id),
                str(pet.user_id),
            )
            continue

        # --- Attempt to create a reminder ---
        # The UNIQUE(preventive_record_id, next_due_date) constraint
        # provides deduplication — if a reminder already exists for this
        # record and due date, the insert will raise IntegrityError.
        try:
            reminder = Reminder(
                preventive_record_id=record.id,
                next_due_date=record.next_due_date,
                status="pending",
            )
            db.add(reminder)
            db.flush()  # Flush to trigger UNIQUE constraint check.

            results["reminders_created"] += 1

            logger.info(
                "Reminder created: record_id=%s, pet_id=%s, "
                "next_due=%s, status=%s",
                str(record.id),
                str(record.pet_id),
                str(record.next_due_date),
                record.status,
            )

        except IntegrityError:
            # Duplicate reminder — already exists for this record + due date.
            # This is expected behavior for stateless re-runs.
            db.rollback()
            results["reminders_skipped"] += 1

            logger.info(
                "Reminder already exists (dedup): record_id=%s, next_due=%s",
                str(record.id),
                str(record.next_due_date),
            )

        except Exception as e:
            # Unexpected error — log and continue to next record.
            # The reminder engine must never crash on individual record failures.
            db.rollback()
            results["errors"] += 1

            logger.error(
                "Error creating reminder for record_id=%s: %s",
                str(record.id),
                str(e),
            )

    # Commit all successfully created reminders.
    db.commit()

    logger.info(
        "Reminder engine completed: checked=%d, created=%d, "
        "skipped=%d, errors=%d",
        results["records_checked"],
        results["reminders_created"],
        results["reminders_skipped"],
        results["errors"],
    )

    return results


def send_pending_reminders(db: Session) -> dict:
    """
    Send WhatsApp template messages for all pending reminders.

    This function processes reminders with status='pending' and sends
    the appropriate WhatsApp template. After sending, it updates the
    reminder status to 'sent' and records the sent_at timestamp.

    Template selection:
        - 'upcoming' records → WHATSAPP_TEMPLATE_REMINDER
        - 'overdue' records → WHATSAPP_TEMPLATE_OVERDUE

    WhatsApp delivery is best-effort:
        - Uses retry_whatsapp_call (1 retry, never raises).
        - If sending fails, the reminder stays 'pending' for the next run.
        - Failures are logged but never crash the engine.

    Rate limiting (MAX_MESSAGES_PER_MINUTE per number) should be
    enforced by the WhatsApp sending utility — not in this function.

    Args:
        db: SQLAlchemy database session.

    Returns:
        Dictionary with sending results:
            - reminders_sent: successfully sent count
            - reminders_failed: failed to send count
    """
    results = {
        "reminders_sent": 0,
        "reminders_failed": 0,
    }

    # Find all pending reminders that need to be sent.
    pending_reminders = (
        db.query(Reminder)
        .filter(Reminder.status == "pending")
        .all()
    )

    for reminder in pending_reminders:
        # Load the preventive record to determine which template to use.
        record = (
            db.query(PreventiveRecord)
            .filter(PreventiveRecord.id == reminder.preventive_record_id)
            .first()
        )

        if not record:
            logger.warning(
                "Preventive record not found for reminder_id=%s. Skipping.",
                str(reminder.id),
            )
            results["reminders_failed"] += 1
            continue

        # Load pet and user for the WhatsApp message recipient.
        pet = db.query(Pet).filter(Pet.id == record.pet_id).first()
        if not pet:
            logger.warning(
                "Pet not found for reminder_id=%s. Skipping.",
                str(reminder.id),
            )
            results["reminders_failed"] += 1
            continue

        user = db.query(User).filter(User.id == pet.user_id).first()
        if not user:
            logger.warning(
                "User not found for reminder_id=%s. Skipping.",
                str(reminder.id),
            )
            results["reminders_failed"] += 1
            continue

        # Load the preventive master item name for the message.
        master = (
            db.query(PreventiveMaster)
            .filter(PreventiveMaster.id == record.preventive_master_id)
            .first()
        )

        # Send the WhatsApp reminder/overdue template via Cloud API.
        # Template selection: upcoming → TEMPLATE_REMINDER, overdue → TEMPLATE_OVERDUE.
        # retry_whatsapp_call handles retries (1 retry, never raises).
        from app.services.whatsapp_sender import send_reminder_message

        try:
            send_result = asyncio.get_event_loop().run_until_complete(
                send_reminder_message(
                    db=db,
                    to_number=user.mobile_number,
                    pet_name=pet.name,
                    item_name=master.item_name if master else "unknown",
                    due_date=str(reminder.next_due_date),
                    record_status=record.status,
                )
            )
        except RuntimeError:
            # If no event loop exists (sync context), create one.
            send_result = asyncio.run(
                send_reminder_message(
                    db=db,
                    to_number=user.mobile_number,
                    pet_name=pet.name,
                    item_name=master.item_name if master else "unknown",
                    due_date=str(reminder.next_due_date),
                    record_status=record.status,
                )
            )

        if send_result:
            reminder.status = "sent"
            reminder.sent_at = datetime.now(IST)
            results["reminders_sent"] += 1

            logger.info(
                "Reminder sent: reminder_id=%s, pet=%s, user=%s, "
                "item=%s, due=%s, record_status=%s",
                str(reminder.id),
                pet.name,
                user.mobile_number,
                master.item_name if master else "unknown",
                str(reminder.next_due_date),
                record.status,
            )
        else:
            # WhatsApp sending failed — reminder stays 'pending' for next run.
            results["reminders_failed"] += 1
            logger.warning(
                "Reminder send failed: reminder_id=%s, pet=%s, user=%s",
                str(reminder.id),
                pet.name,
                user.mobile_number,
            )

    db.commit()

    logger.info(
        "Reminder sending completed: sent=%d, failed=%d",
        results["reminders_sent"],
        results["reminders_failed"],
    )

    return results
