"""
PetCircle Phase 1 — Internal Router

Provides internal-only endpoints for cron jobs and system operations.
These endpoints are NOT exposed to users — they are called by Render
cron jobs or admin scripts.

Routes:
    POST /internal/run-reminder-engine — Execute daily reminder processing.
        Also runs conflict expiry check (Module 19).

Security:
    - Protected by the same X-ADMIN-KEY header as admin routes.
    - Render cron jobs must include the admin key in their requests.
    - No public access.
"""

import logging
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.core.security import validate_admin_key
from app.core.rate_limiter import check_admin_rate_limit
from app.services.reminder_engine import run_reminder_engine, send_pending_reminders
from app.services.conflict_expiry import expire_pending_conflicts


logger = logging.getLogger(__name__)


# All routes require admin authentication and IP-based rate limiting.
# Render cron jobs must include X-ADMIN-KEY header.
router = APIRouter(
    prefix="/internal",
    tags=["internal"],
    dependencies=[Depends(check_admin_rate_limit), Depends(validate_admin_key)],
)


@router.post("/run-reminder-engine")
def execute_reminder_engine(db: Session = Depends(get_db)):
    """
    Execute the daily reminder engine and conflict expiry.

    This endpoint is called by Render cron at 8 AM IST daily.
    It performs two operations in sequence:

    1. Conflict expiry (Module 19):
        - Auto-resolve pending conflicts older than 5 days.
        - Strategy: KEEP_EXISTING, status='auto_resolved'.

    2. Reminder creation (Module 10):
        - Find preventive records with 'upcoming' or 'overdue' status.
        - Create reminders (deduplicated by UNIQUE constraint).

    3. Reminder sending (Module 10):
        - Send WhatsApp templates for pending reminders.
        - Update status to 'sent' with sent_at timestamp.

    Conflict expiry runs first to ensure stale conflicts are resolved
    before the reminder engine processes records.

    Returns:
        Combined results from all three operations.
    """
    # --- Step 1: Expire stale conflicts ---
    # Run conflict expiry first so that auto-resolved conflicts
    # don't interfere with reminder processing.
    conflicts_resolved = expire_pending_conflicts(db)

    # --- Step 2: Create reminders for due records ---
    reminder_results = run_reminder_engine(db)

    # --- Step 3: Send pending reminders ---
    send_results = send_pending_reminders(db)

    logger.info(
        "Daily cron completed: conflicts_resolved=%d, "
        "reminders_created=%d, reminders_sent=%d",
        conflicts_resolved,
        reminder_results["reminders_created"],
        send_results["reminders_sent"],
    )

    return {
        "conflicts_resolved": conflicts_resolved,
        "reminder_engine": reminder_results,
        "reminder_sending": send_results,
    }
