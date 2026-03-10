"""
PetCircle Phase 1 — Message Router

Routes incoming WhatsApp messages to the appropriate service handler
based on message type, user state, and conversation context.

Routing logic:
    1. New user (no DB record) → Create pending user, start onboarding
    2. User in onboarding (state != 'complete') → Continue onboarding
    3. Button payload (reminder) → Reminder response handler
    4. Button payload (conflict) → Conflict resolution handler
    5. Image/Document → Document upload + GPT extraction pipeline
    6. Text "add pet" → Start new pet onboarding
    7. Text "dashboard" → Send dashboard links
    8. Text → Query engine (pet health questions)

Rules:
    - No business logic in this file — only routing decisions.
    - Errors are caught and friendly messages sent back.
    - Never crashes on individual message failures.
"""

import asyncio
import logging
import time
from sqlalchemy.orm import Session
from app.config import settings
from app.core.encryption import decrypt_field
from app.core.log_sanitizer import mask_phone
from app.utils.breed_fun_facts import get_breed_fun_fact
from app.core.constants import (
    REMINDER_DONE,
    REMINDER_SNOOZE_7,
    REMINDER_RESCHEDULE,
    REMINDER_CANCEL,
    CONFLICT_USE_NEW,
    CONFLICT_KEEP_EXISTING,
    MAX_PETS_PER_USER,
    MAX_PENDING_DOCS_PER_PET,
    MAX_CONCURRENT_EXTRACTIONS,
    GREETINGS,
    ACKNOWLEDGMENTS,
    FAREWELLS,
    HELP_COMMANDS,
)

# Semaphore to limit concurrent background extraction tasks.
# Prevents DB connection pool exhaustion when many documents are uploaded.
_extraction_semaphore = asyncio.Semaphore(MAX_CONCURRENT_EXTRACTIONS)

# --- Batch upload tracking ---
# Tracks recent upload timestamps per pet to enforce the 5-file batch limit.
# Key: str(pet_id), Value: list of upload timestamps (epoch seconds).
# This is in-memory to avoid DB race conditions when many files arrive at once.
_recent_uploads: dict[str, list[float]] = {}

# Tracks whether a batch rejection message was already sent for a pet.
# Prevents spamming the user with repeated "too many files" messages.
# Key: str(pet_id), Value: True if rejection was sent this batch.
_rejection_sent: dict[str, bool] = {}

# Tracks whether a generic error message was recently sent to a user.
# Prevents spamming "Sorry, something went wrong" during webhook retries.
# Key: from_number, Value: True if error was recently sent
_error_sent: dict[str, bool] = {}

# Window in seconds for counting a "batch" of uploads.
# Files uploaded within this window are considered one batch.
_UPLOAD_BATCH_WINDOW_SECONDS: int = 120

# Debounce timers for batch extraction per pet.
# Key: str(pet_id), Value: asyncio.Task that waits then extracts.
_extraction_timers: dict[str, asyncio.Task] = {}

# Tracks document IDs uploaded in the active WhatsApp batch per pet.
# Ensures the extractor only processes files from the current user upload burst,
# and avoids including unrelated pending documents from other channels.
# Key: str(pet_id), Value: list of Document.id values.
_batch_document_ids: dict[str, list] = {}

# Seconds to wait after the last upload before starting batch extraction.
# Gives the user time to finish sending all files in a batch.
_EXTRACTION_DELAY_SECONDS: int = 15
from app.services.onboarding import (
    get_or_create_user,
    create_pending_user,
    handle_onboarding_step,
    is_doc_upload_deadline_expired,
)
from app.services.whatsapp_sender import (
    send_text_message,
    download_whatsapp_media,
)
from app.models.pet import Pet
from app.models.document import Document
from app.models.reminder import Reminder
from app.models.conflict_flag import ConflictFlag


logger = logging.getLogger(__name__)


def _get_mobile(user) -> str:
    """
    Get the plaintext mobile number for sending messages.

    Prefers the cached plaintext from the current request (set by route_message).
    Falls back to decrypting the stored encrypted mobile_number.
    """
    return getattr(user, "_plaintext_mobile", None) or decrypt_field(user.mobile_number)


# All valid reminder payload IDs
REMINDER_PAYLOADS = {REMINDER_DONE, REMINDER_SNOOZE_7, REMINDER_RESCHEDULE, REMINDER_CANCEL}

# All valid conflict payload IDs
CONFLICT_PAYLOADS = {CONFLICT_USE_NEW, CONFLICT_KEEP_EXISTING}


async def route_message(db: Session, message_data: dict) -> None:
    """
    Route an incoming WhatsApp message to the appropriate handler.

    Args:
        db: SQLAlchemy database session.
        message_data: Flat dictionary from webhook's _extract_message_data().
    """
    from_number = message_data.get("from_number")
    msg_type = message_data.get("type")

    if not from_number:
        logger.warning("Message has no from_number — skipping.")
        return

    # Silently ignore non-actionable message types (reactions, stickers,
    # location, contacts, etc.) — these should never trigger onboarding
    # prompts or GPT calls.
    _ACTIONABLE_TYPES = {"text", "image", "document", "button"}
    if msg_type not in _ACTIONABLE_TYPES:
        logger.info("Ignoring non-actionable message type '%s' from %s", msg_type, mask_phone(from_number))
        return

    try:
        # --- Step 1: Look up or create user ---
        user, is_existing = get_or_create_user(db, from_number)

        if not is_existing:
            # Brand new user — create pending record, send welcome.
            # create_pending_user handles race conditions: if another webhook
            # already created this user, it returns the existing record.
            user = create_pending_user(db, from_number)

            # Only send welcome if user is truly new (awaiting_consent).
            # If race condition returned an existing user mid-onboarding, skip welcome.
            if user.onboarding_state == "awaiting_consent":
                await send_text_message(
                    db, from_number,
                    "Hey there! Welcome to *PetCircle* 🐾\n\n"
                    "I'm your pet's personal health assistant. I help you stay on top of "
                    "vaccinations, deworming, tick treatments, and all the preventive care "
                    "your furry friend needs — right here on WhatsApp.\n\n"
                    "Before we begin, I need your consent to store your pet's health data "
                    "so I can send you timely reminders and keep everything organized.\n\n"
                    "Reply *yes* to get started or *no* to opt out.",
                )
                return
            # Otherwise fall through to handle user as existing.

        # Attach plaintext number for downstream sending.
        # user.mobile_number is encrypted in DB; from_number is plaintext from webhook.
        user._plaintext_mobile = from_number

        # --- Step 2: Check if user is still onboarding ---
        if user.onboarding_state and user.onboarding_state != "complete":

            # --- Special handling for awaiting_documents state ---
            # During the upload window, allow image/document uploads alongside text.
            if user.onboarding_state == "awaiting_documents":
                

                # Check deadline expiry on any incoming message.
                if is_doc_upload_deadline_expired(user.doc_upload_deadline):    
                    from app.services.onboarding import _finalize_onboarding
                    await _finalize_onboarding(db, user, send_text_message)
                    return
                # Allow document/image uploads during this state.
                if msg_type in ("image", "document"):
                    await _handle_media(db, user, message_data)
                    return
                # Text input → route to onboarding handler (handles "skip" + rejection).
                text = (message_data.get("text") or "").strip()
                if text:
                    await handle_onboarding_step(db, user, text, send_text_message, message_data=message_data)
                return

            # --- All other onboarding states: block non-text ---
            text = (message_data.get("text") or "").strip()
            if not text:
                # Only send the "please send text" prompt once per user.
                # Check message_logs for whether we already sent it.
                # If already sent, silently ignore non-text messages.
                from sqlalchemy import cast, String
                from app.models.message_log import MessageLog
                already_sent = (
                    db.query(MessageLog.id)
                    .filter(
                        MessageLog.mobile_number == from_number,
                        MessageLog.direction == "outgoing",
                        MessageLog.message_type == "text",
                        cast(MessageLog.payload["text"]["body"], String).like(
                            "%Please send a text%"
                        ),
                    )
                    .first()
                )
                if not already_sent:
                    await send_text_message(
                        db, from_number,
                        "Please send a text message to continue setup.",
                    )
                return
            await handle_onboarding_step(db, user, text, send_text_message, message_data=message_data)
            return

        # --- Step 3: User is fully onboarded — route by message type ---
        if msg_type == "button":
            await _handle_button(db, user, message_data)

        elif msg_type in ("image", "document"):
            await _handle_media(db, user, message_data)

        elif msg_type == "text":
            await _handle_text(db, user, message_data)

        else:
            # Safety net — non-actionable types are filtered at the top of
            # route_message(), so this branch should be unreachable.
            logger.info("Unhandled message type '%s' from %s", msg_type, mask_phone(from_number))

        # Clear error state on successful processing
        _error_sent.pop(from_number, None)

    except Exception as e:
        logger.error("Error routing message from %s: %s", mask_phone(from_number), str(e))
        # Rollback any dirty transaction state before attempting to send error message.
        try:
            db.rollback()
        except Exception:
            pass
        try:
            if not _error_sent.get(from_number):
                _error_sent[from_number] = True
                await send_text_message(
                    db, from_number,
                    "Sorry, something went wrong. Please try again.",
                )
        except Exception:
            pass


async def _handle_text(db: Session, user, message_data: dict) -> None:
    """
    Handle a text message from a fully onboarded user.

    Routing (in order):
        1. Empty text → ignore
        2. Pending reschedule → apply_reschedule_date()
        3. Greeting → canned menu
        4. Acknowledgment (thanks, ok) → canned reply
        5. Farewell (bye) → canned reply
        6. Help/menu → show commands
        7. "add pet" / "new pet" → start new pet onboarding
        8. "dashboard" / "link" → send dashboard links
        9. anything else → query engine
    """
    text = (message_data.get("text") or "").strip()
    text_lower = text.lower()
    from_number = _get_mobile(user)

    # --- Guard: empty text should not trigger GPT ---
    if not text:
        return

    # --- Check for pending reschedule before any other routing ---
    # If user recently pressed "Reschedule" on a reminder, route the
    # next text message as a date input to apply_reschedule_date().
    reschedule_result = await _try_handle_reschedule_date(db, user, text, from_number)
    if reschedule_result:
        return

    # --- Greeting — canned menu, no GPT call ---
    if text_lower in GREETINGS:
        await _send_help_menu(db, from_number)
        return

    # --- Acknowledgments (thanks, ok, got it) — canned reply ---
    if text_lower in ACKNOWLEDGMENTS:
        await send_text_message(
            db, from_number,
            "You're welcome! Let me know if you need anything else.",
        )
        return

    # --- Farewells (bye, see you) — canned reply ---
    if text_lower in FAREWELLS:
        await send_text_message(
            db, from_number,
            "Bye! I'm always here when you need me. Take care! 🐾",
        )
        return

    # --- Help / Menu — show available commands ---
    if text_lower in HELP_COMMANDS:
        await _send_help_menu(db, from_number)
        return

    # "add pet" command — restart pet portion of onboarding
    if text_lower in ("add pet", "new pet", "add another pet"):
        pet_count = (
            db.query(Pet)
            .filter(Pet.user_id == user.id, Pet.is_deleted == False)
            .count()
        )
        if pet_count >= MAX_PETS_PER_USER:
            await send_text_message(
                db, from_number,
                f"You already have {pet_count} pets registered. "
                f"Maximum is {MAX_PETS_PER_USER}.",
            )
        else:
            user.onboarding_state = "awaiting_pet_name"
            db.commit()
            await send_text_message(
                db, from_number,
                "Let's add another pet! What is your pet's *name*?",
            )
        return

    # "dashboard" / "link" command — exact match or phrase detection.
    # Handles: "dashboard", "link", "my dashboard", "send me the link",
    # "send dashboard link", "show link for ahu", etc.
    # Word-boundary check avoids false positives like "blinking".
    _dashboard_exact = {"dashboard", "link", "my dashboard"}
    _dashboard_phrases = ("dashboard", " link", "link ")
    if text_lower in _dashboard_exact or text_lower.startswith("link") or any(
        phrase in text_lower for phrase in _dashboard_phrases
    ):
        await _send_dashboard_links(db, user)
        return

    # General query — route to GPT query engine
    await _handle_query(db, user, text)


async def _send_help_menu(db: Session, from_number: str) -> None:
    """Send the help/commands menu to the user."""
    await send_text_message(
        db, from_number,
        "Hi there! How can I help you today? 🐾\n\n"
        "You can:\n"
        "• Ask me anything about your pet's health\n"
        "• Send *add pet* to register another pet\n"
        "• Send *dashboard* to view your pet's records\n"
        "• Send *help* to see this menu\n"
        "• Upload a vet document for extraction",
    )


async def _try_handle_reschedule_date(
    db: Session, user, text: str, from_number: str,
) -> bool:
    """
    Check if user has a pending reschedule and route date input accordingly.

    A reschedule is pending when a reminder is in 'sent' status and the
    most recent outgoing message was the reschedule date prompt. This avoids
    adding an extra DB column — we detect the state from existing data.

    Returns True if the message was consumed as a reschedule date, False otherwise.
    """
    from app.services.reminder_response import apply_reschedule_date
    from app.models.preventive_record import PreventiveRecord
    from app.utils.date_utils import parse_date
    from app.models.message_log import MessageLog
    from sqlalchemy import cast, String

    # Check if the last outgoing message was the reschedule date prompt.
    last_outgoing = (
        db.query(MessageLog)
        .filter(
            MessageLog.mobile_number == from_number,
            MessageLog.direction == "outgoing",
            MessageLog.message_type == "text",
        )
        .order_by(MessageLog.created_at.desc())
        .first()
    )

    if not last_outgoing:
        return False

    # Check if the last outgoing message contains the reschedule prompt text.
    payload_body = ""
    try:
        payload_body = last_outgoing.payload.get("text", {}).get("body", "")
    except (AttributeError, TypeError):
        return False

    if "new date" not in payload_body.lower() or "DD/MM/YYYY" not in payload_body:
        return False

    # Find the sent reminder this reschedule is for.
    reminder = (
        db.query(Reminder)
        .join(PreventiveRecord, Reminder.preventive_record_id == PreventiveRecord.id)
        .join(Pet, PreventiveRecord.pet_id == Pet.id)
        .filter(
            Pet.user_id == user.id,
            Pet.is_deleted == False,
            Reminder.status == "sent",
        )
        .order_by(Reminder.sent_at.desc())
        .first()
    )

    if not reminder:
        return False

    # Try to parse the user's text as a date.
    try:
        new_date = parse_date(text.strip())
    except ValueError:
        await send_text_message(
            db, from_number,
            "Invalid date format. Please use DD/MM/YYYY or DD-MM-YYYY.",
        )
        return True  # Consumed the message (even though it failed)

    try:
        result = apply_reschedule_date(db, reminder.id, new_date)
        await send_text_message(
            db, from_number,
            f"Rescheduled! New due date: {result.get('new_due_date', 'N/A')}",
        )
    except ValueError as e:
        await send_text_message(db, from_number, str(e))

    return True


async def _handle_button(db: Session, user, message_data: dict) -> None:
    """Handle a button response — route to reminder or conflict handler."""
    payload = message_data.get("button_payload", "")
    from_number = _get_mobile(user)

    if payload in REMINDER_PAYLOADS:
        await _handle_reminder_button(db, user, payload)
    elif payload in CONFLICT_PAYLOADS:
        await _handle_conflict_button(db, user, payload)
    else:
        logger.warning("Unknown button payload '%s' from %s", payload, from_number)
        await send_text_message(
            db, from_number,
            "Sorry, I didn't understand that response.",
        )


async def _handle_reminder_button(db: Session, user, payload: str) -> None:
    """Handle a reminder button response."""
    from app.services.reminder_response import handle_reminder_response
    from app.models.preventive_record import PreventiveRecord

    from_number = _get_mobile(user)

    # Find the latest sent reminder for this user's pets via direct JOIN
    # (avoids separate pet query).
    reminder = (
        db.query(Reminder)
        .join(PreventiveRecord, Reminder.preventive_record_id == PreventiveRecord.id)
        .join(Pet, PreventiveRecord.pet_id == Pet.id)
        .filter(
            Pet.user_id == user.id,
            Pet.is_deleted == False,
            Reminder.status == "sent",
        )
        .order_by(Reminder.sent_at.desc())
        .first()
    )

    if not reminder:
        await send_text_message(db, from_number, "No active reminder found to respond to.")
        return

    try:
        result = handle_reminder_response(db, reminder.id, payload)

        if payload == REMINDER_DONE:
            await send_text_message(
                db, from_number,
                f"Marked as done! Next due: {result.get('next_due_date', 'N/A')}",
            )
        elif payload == REMINDER_SNOOZE_7:
            await send_text_message(
                db, from_number,
                f"Snoozed for 7 days. New due: {result.get('new_due_date', 'N/A')}",
            )
        elif payload == REMINDER_RESCHEDULE:
            await send_text_message(
                db, from_number,
                "Please send the new date (DD/MM/YYYY or DD-MM-YYYY).",
            )
        elif payload == REMINDER_CANCEL:
            await send_text_message(db, from_number, "Reminder cancelled.")

    except ValueError as e:
        await send_text_message(db, from_number, str(e))


async def _handle_conflict_button(db: Session, user, payload: str) -> None:
    """Handle a conflict resolution button response."""
    from app.services.conflict_engine import resolve_conflict
    from app.models.preventive_record import PreventiveRecord

    from_number = _get_mobile(user)

    # Find the latest pending conflict for this user's pets via direct JOIN
    # (avoids separate pet query).
    conflict = (
        db.query(ConflictFlag)
        .join(PreventiveRecord, ConflictFlag.preventive_record_id == PreventiveRecord.id)
        .join(Pet, PreventiveRecord.pet_id == Pet.id)
        .filter(
            Pet.user_id == user.id,
            Pet.is_deleted == False,
            ConflictFlag.status == "pending",
        )
        .order_by(ConflictFlag.created_at.desc())
        .first()
    )

    if not conflict:
        await send_text_message(db, from_number, "No pending conflicts found.")
        return

    try:
        resolve_conflict(db, conflict.id, payload)
        if payload == CONFLICT_USE_NEW:
            await send_text_message(db, from_number, "Updated to the new date.")
        else:
            await send_text_message(db, from_number, "Kept the existing date.")
    except ValueError as e:
        await send_text_message(db, from_number, str(e))


async def _handle_media(db: Session, user, message_data: dict) -> None:
    """
    Handle image or document uploads with batch limiting.

    Enforces a strict per-pet batch limit (MAX_PENDING_DOCS_PER_PET) using
    an in-memory counter to avoid DB race conditions when many files arrive
    concurrently. Files beyond the limit are rejected BEFORE downloading.

    Extraction is deferred: after the last upload in a batch settles
    (no new files for _EXTRACTION_DELAY_SECONDS), all pending documents
    for the pet are extracted together. This prevents per-file GPT calls
    from exhausting DB connections and API rate limits.
    """
    from app.services.document_upload import process_document_upload

    from_number = _get_mobile(user)
    media_id = message_data.get("media_id")
    original_filename = message_data.get("filename")
    caption = message_data.get("caption")

    if not media_id:
        await send_text_message(db, from_number, "Couldn't process that file. Please try again.")
        return

    # If the document/image was sent without any caption, that's fine —
    # but log it so we can track standalone uploads vs. captioned ones.
    if not caption:
        logger.info(
            "Document sent without caption from %s (media_id=%s)",
            mask_phone(from_number), media_id,
        )

    # Find user's most recent active pet.
    pet = (
        db.query(Pet)
        .filter(Pet.user_id == user.id, Pet.is_deleted == False)
        .order_by(Pet.created_at.desc())
        .first()
    )

    if not pet:
        await send_text_message(db, from_number, "Please register a pet first.")
        return

    # --- Ghost record prevention ---
    # Primary dedup: check if a Document with this wamid already exists.
    # This is the strongest dedup — one Document per WhatsApp message,
    # regardless of filename, media_id, or server restarts.
    message_id = message_data.get("message_id")

    if message_id:
        existing_by_wamid = (
            db.query(Document.id)
            .filter(Document.source_wamid == message_id)
            .first()
        )
        if existing_by_wamid:
            logger.info(
                "Duplicate document detected (wamid dedup): wamid=%s, "
                "pet_id=%s — skipping.",
                message_id, str(pet.id),
            )
            return

    # Secondary dedup: check by filename or media_id as fallback.
    from datetime import datetime, timedelta
    dedup_cutoff = datetime.utcnow() - timedelta(hours=24)

    if original_filename:
        existing_doc = (
            db.query(Document.id)
            .filter(
                Document.pet_id == pet.id,
                Document.document_name == original_filename,
                Document.created_at >= dedup_cutoff,
            )
            .first()
        )
        if existing_doc:
            logger.info(
                "Duplicate document detected (filename dedup): filename=%s, "
                "pet_id=%s, message_id=%s — skipping.",
                original_filename, str(pet.id), message_id,
            )
            return
    elif media_id:
        existing_doc = (
            db.query(Document.id)
            .filter(
                Document.pet_id == pet.id,
                Document.file_path.like(f"%{media_id}%"),
                Document.created_at >= dedup_cutoff,
            )
            .first()
        )
        if existing_doc:
            logger.info(
                "Duplicate image detected (media_id dedup): media_id=%s, "
                "pet_id=%s, message_id=%s — skipping.",
                media_id, str(pet.id), message_id,
            )
            return

    # --- Batch limit check (in-memory, race-safe) ---
    # Count recent uploads for this pet within the batch window.
    pet_key = str(pet.id)
    now = time.time()
    cutoff = now - _UPLOAD_BATCH_WINDOW_SECONDS

    # Clean up old entries outside the batch window.
    if pet_key in _recent_uploads:
        _recent_uploads[pet_key] = [
            ts for ts in _recent_uploads[pet_key] if ts > cutoff
        ]
    else:
        _recent_uploads[pet_key] = []

    recent_count = len(_recent_uploads[pet_key])

    if recent_count >= MAX_PENDING_DOCS_PER_PET:
        # Only send the rejection message once per batch to avoid spamming.
        if not _rejection_sent.get(pet_key):
            _rejection_sent[pet_key] = True
            await send_text_message(
                db, from_number,
                f"Too many files! You've sent {recent_count} documents for "
                f"{pet.name} already.\n\n"
                f"Please upload maximum *{MAX_PENDING_DOCS_PER_PET} files at a time* "
                f"and wait for extraction to finish before sending more.",
            )
        return

    # Track this upload in the in-memory batch window.
    _recent_uploads[pet_key].append(now)

    # --- Download media from WhatsApp ---
    media_result = await download_whatsapp_media(media_id)
    if not media_result:
        # Remove the tracked upload since download failed.
        _recent_uploads[pet_key].pop()
        await send_text_message(db, from_number, "Failed to download the file. Please try again.")
        return

    file_content, detected_mime = media_result

    try:
        filename = original_filename or f"{media_id}.{_mime_to_ext(detected_mime)}"
        document = await process_document_upload(
            db=db,
            pet_id=pet.id,
            user_id=user.id,
            filename=filename,
            file_content=file_content,
            mime_type=detected_mime,
            pet_name=pet.name,
            source_wamid=message_id,
        )

        await send_text_message(
            db, from_number,
            f"*{display_name}* saved for *{pet.name}*. "
            f"Will start extracting health data once all files are received.",
        )

        # Track this exact document in the current in-memory batch so the
        # deferred extractor doesn't accidentally sweep unrelated pending docs.
        _batch_document_ids.setdefault(pet_key, []).append(document.id)

        # Schedule (or reschedule) a deferred batch extraction.
        # The timer resets with each new upload so extraction only starts
        # after uploads have settled (_EXTRACTION_DELAY_SECONDS of silence).
        _schedule_batch_extraction(
            pet_id=pet.id,
            pet_name=pet.name,
            user_id=user.id,
            from_number=from_number,
        )

    except ValueError as e:
        # Remove the tracked upload since storage failed.
        _recent_uploads[pet_key].pop()
        await send_text_message(db, from_number, str(e))
    except RuntimeError:
        _recent_uploads[pet_key].pop()
        await send_text_message(db, from_number, "Upload failed. Please try again later.")


def _schedule_batch_extraction(
    pet_id, pet_name, user_id, from_number,
) -> None:
    """
    Schedule (or reschedule) a deferred batch extraction for a pet.

    Each new upload resets the timer. Extraction only starts after
    _EXTRACTION_DELAY_SECONDS of no new uploads, ensuring the full
    batch is received before processing begins.
    """
    pet_key = str(pet_id)

    # Cancel existing timer for this pet (debounce).
    existing = _extraction_timers.get(pet_key)
    if existing and not existing.done():
        existing.cancel()

    # Schedule a new delayed extraction.
    _extraction_timers[pet_key] = asyncio.create_task(
        _delayed_batch_extraction(pet_id, pet_name, user_id, from_number)
    )


async def _delayed_batch_extraction(
    pet_id, pet_name, user_id, from_number,
) -> None:
    """
    Wait for uploads to settle, then extract all pending documents for the pet.

    Waits _EXTRACTION_DELAY_SECONDS, then queries all pending documents
    for the pet and extracts them one-by-one (each under the semaphore).
    Sends a single batch summary when all extractions are done.
    """
    await asyncio.sleep(_EXTRACTION_DELAY_SECONDS)

    pet_key = str(pet_id)

    # Clean up the extraction timer entry.
    _extraction_timers.pop(pet_key, None)

    from app.database import get_fresh_session
    from app.services.gpt_extraction import extract_and_process_document

    bg_db = get_fresh_session()
    try:
        # Fetch only documents explicitly uploaded in this WhatsApp batch.
        # This prevents unrelated pending documents (e.g. dashboard uploads)
        # from being included in the current extraction summary.
        batched_doc_ids = list(_batch_document_ids.get(pet_key, []))
        if not batched_doc_ids:
            return

        pending_docs = (
            bg_db.query(Document)
            .filter(
                Document.pet_id == pet_id,
                Document.extraction_status == "pending",
                Document.id.in_(batched_doc_ids),
            )
            .order_by(Document.created_at.asc())
            .all()
        )

        if not pending_docs:
            return

        total = len(pending_docs)
        logger.info(
            "Starting batch extraction for pet %s: %d pending documents",
            str(pet_id), total,
        )

        # Notify user once per batch with consolidated acknowledgements.
        doc_names = "\n".join(f"  - {d.document_name or d.file_path.split('/')[-1]}" for d in pending_docs)
        pet = bg_db.query(Pet).filter(Pet.id == pet_id).first()
        pet_species = pet.species if pet else "dog"
        pet_breed = pet.breed if pet else None
        fun_fact = await get_breed_fun_fact(bg_db, user_id, pet_breed, pet_species)
        await send_text_message(
            bg_db, from_number,
            f"Got it — I received *{total}* document{'s' if total != 1 else ''} for *{pet_name}*:\n{doc_names}\n\n"
            f"Fun fact: {fun_fact}",
        )
        await send_text_message(
            bg_db, from_number,
            f"I will now start extracting health data for *{pet_name}*:\n{doc_names}\n\n"
            f"Fun fact: {fun_fact}",
        )

        last_result = None
        success_count = 0
        fail_count = 0
        failed_doc_names = []
        all_results = []

        # Extract each document sequentially under the semaphore.
        # Each extraction is given a 120s timeout to prevent one stuck GPT
        # call from blocking the entire pipeline for all other users.
        for idx, doc in enumerate(pending_docs, 1):
            async with _extraction_semaphore:
                try:
                    # Download actual file content from Supabase for GPT processing.
                    from app.services.document_upload import download_from_supabase
                    file_bytes = await download_from_supabase(doc.file_path)

                    if not file_bytes:
                        fail_count += 1
                        doc_label = doc.document_name or doc.file_path.split("/")[-1]
                        failed_doc_names.append(doc_label)
                        doc.extraction_status = "failed"
                        bg_db.commit()
                        continue

                    result = await asyncio.wait_for(
                        extract_and_process_document(
                            bg_db, doc.id,
                            f"[file: {doc.file_path}]",
                            file_bytes=file_bytes,
                        ),
                        timeout=120,
                    )
                    all_results.append(result)

                    if result.get("status") == "failed":
                        fail_count += 1
                        doc_label = doc.document_name or doc.file_path.split("/")[-1]
                        # Only show document name — no error details to the user.
                        failed_doc_names.append(doc_label)
                    else:
                        last_result = result
                        success_count += 1

                    logger.info(
                        "Extracted doc %d/%d (id=%s) for pet %s: status=%s",
                        idx, total, str(doc.id), str(pet_id),
                        result.get("status"),
                    )
                except asyncio.TimeoutError:
                    fail_count += 1
                    doc_label = doc.document_name or doc.file_path.split("/")[-1]
                    failed_doc_names.append(doc_label)
                    logger.error(
                        "Extraction timed out for doc %s (%d/%d) pet %s",
                        str(doc.id), idx, total, str(pet_id),
                    )
                    try:
                        doc.extraction_status = "failed"
                        bg_db.commit()
                    except Exception:
                        try:
                            bg_db.rollback()
                        except Exception:
                            pass
                except Exception as e:
                    fail_count += 1
                    doc_label = doc.document_name or doc.file_path.split("/")[-1]
                    failed_doc_names.append(doc_label)
                    logger.error(
                        "Extraction failed for doc %s (%d/%d): %s",
                        str(doc.id), idx, total, str(e),
                    )
                    try:
                        bg_db.rollback()
                    except Exception:
                        pass
                    # Mark as failed so it doesn't get re-extracted in
                    # future batches. Without this, the document stays
                    # 'pending' and gets picked up by the next upload's
                    # batch extraction — causing ghost re-processing.
                    try:
                        doc.extraction_status = "failed"
                        bg_db.commit()
                    except Exception:
                        try:
                            bg_db.rollback()
                        except Exception:
                            pass

        # --- Send ONE consolidated summary after all extractions complete ---
        pet = bg_db.query(Pet).filter(Pet.id == pet_id).first()
        from app.models.user import User
        user = bg_db.query(User).filter(User.id == user_id).first()

        if user and pet:
            user._plaintext_mobile = from_number
            await _send_batch_summary(
                bg_db, user, pet, from_number,
                all_results, success_count, fail_count, failed_doc_names,
            )

        # Clear the batch counter and rejection flag so user can upload again.
        _recent_uploads.pop(pet_key, None)
        _rejection_sent.pop(pet_key, None)
        _batch_document_ids.pop(pet_key, None)

    except Exception as e:
        logger.error(
            "Batch extraction failed for pet %s: %s", str(pet_id), str(e),
        )
        try:
            bg_db.rollback()
        except Exception:
            pass
        try:
            await send_text_message(
                bg_db, from_number,
                f"Extraction encountered an issue for {pet_name}. "
                f"Please check the dashboard or try uploading again.",
            )
        except Exception:
            pass
        # Clear batch counter even on failure so user isn't stuck.
        _recent_uploads.pop(pet_key, None)
        _batch_document_ids.pop(pet_key, None)
    finally:
        bg_db.close()


async def _handle_query(db: Session, user, text: str) -> None:
    """Handle a general text query via GPT query engine."""
    from app.services.query_engine import answer_pet_question

    from_number = _get_mobile(user)

    pet = (
        db.query(Pet)
        .filter(Pet.user_id == user.id, Pet.is_deleted == False)
        .order_by(Pet.created_at.desc())
        .first()
    )

    if not pet:
        await send_text_message(db, from_number, "Please register a pet first.")
        return

    try:
        # 45s timeout prevents a stuck GPT call from hanging the user's session.
        result = await asyncio.wait_for(
            answer_pet_question(db, pet.id, text),
            timeout=45,
        )
        answer = result.get("answer", "Sorry, I couldn't find an answer.")
        await send_text_message(db, from_number, answer)
    except asyncio.TimeoutError:
        logger.error("Query engine timed out for pet %s", str(pet.id))
        await send_text_message(
            db, from_number,
            "Your question is taking too long to process. Please try again.",
        )
    except Exception as e:
        logger.error("Query engine error: %s", str(e))
        await send_text_message(
            db, from_number,
            "Sorry, I couldn't process your question. Please try again later.",
        )


async def _send_dashboard_links(db, user) -> None:
    """
    Send dashboard links for all user's pets.

    Auto-regenerates expired or revoked tokens so the user always
    receives a working link.
    """
    from datetime import datetime
    from app.models.dashboard_token import DashboardToken
    from app.services.onboarding import refresh_dashboard_token
    from app.config import settings

    from_number = _get_mobile(user)

    pets = db.query(Pet).filter(
        Pet.user_id == user.id, Pet.is_deleted == False
    ).all()

    if not pets:
        await send_text_message(db, from_number, "No pets found.")
        return

    # Batch-load all active tokens for user's pets to avoid N+1 queries.
    pet_ids = [p.id for p in pets]
    tokens = (
        db.query(DashboardToken)
        .filter(DashboardToken.pet_id.in_(pet_ids), DashboardToken.revoked == False)
        .all()
    )
    token_by_pet = {t.pet_id: t for t in tokens}

    messages = []
    for pet in pets:
        try:
            token_record = token_by_pet.get(pet.id)

            # Auto-refresh if token is expired or missing.
            if token_record and token_record.expires_at and datetime.utcnow() > token_record.expires_at:
                new_token = refresh_dashboard_token(db, pet.id)
                messages.append(f"*{pet.name}'s Dashboard*:\n{settings.FRONTEND_URL}/dashboard/{new_token}")
            elif token_record:
                messages.append(f"*{pet.name}'s Dashboard*:\n{settings.FRONTEND_URL}/dashboard/{token_record.token}")
            else:
                # No token at all — generate a fresh one.
                new_token = refresh_dashboard_token(db, pet.id)
                messages.append(f"*{pet.name}'s Dashboard*:\n{settings.FRONTEND_URL}/dashboard/{new_token}")
        except Exception as e:
            logger.error("Failed to get/refresh token for pet %s: %s", str(pet.id), str(e))
            messages.append(f"*{pet.name}'s Dashboard*: Link temporarily unavailable")
            try:
                db.rollback()
            except Exception:
                pass

    await send_text_message(
        db, from_number,
        "Your pet dashboards:\n\n" + "\n".join(messages),
    )


def _get_dashboard_link(db: Session, pet) -> str | None:
    """
    Get the active dashboard link for a pet.

    Returns the full URL if a valid token exists, None otherwise.
    Auto-refreshes expired tokens. Never raises — returns None on any error.
    """
    try:
        from datetime import datetime
        from app.models.dashboard_token import DashboardToken
        from app.services.onboarding import refresh_dashboard_token

        token_record = (
            db.query(DashboardToken)
            .filter(DashboardToken.pet_id == pet.id, DashboardToken.revoked == False)
            .first()
        )

        if not token_record:
            return None

        # Auto-refresh expired tokens.
        if token_record.expires_at and datetime.utcnow() > token_record.expires_at:
            new_token = refresh_dashboard_token(db, pet.id)
            return f"{settings.FRONTEND_URL}/dashboard/{new_token}"

        return f"{settings.FRONTEND_URL}/dashboard/{token_record.token}"
    except Exception as e:
        logger.error("Failed to get dashboard link for pet %s: %s", str(pet.id), str(e))
        return None


async def _send_batch_summary(
    db: Session, user, pet, from_number: str,
    all_results: list[dict], success_count: int, fail_count: int,
    failed_doc_names: list[str],
) -> None:
    """
    Send ONE consolidated message summarizing the entire batch extraction.

    Rules:
        - If entire batch failed: one error message with dashboard link.
        - If partial failure: list which docs failed by name.
        - If all succeeded: show extraction summary with items found.
    """
    total = success_count + fail_count

    # --- Check for non-pet document results ---
    # If any result indicates a non-pet document, send a specific message.
    not_pet_results = [
        r for r in all_results
        if r.get("document_type") == "not_pet_related"
    ]
    if not_pet_results:
        not_pet_errors = []
        for r in not_pet_results:
            errs = [e for e in r.get("errors", []) if "pet/veterinary" in e]
            not_pet_errors.extend(errs)
        if not_pet_errors:
            await send_text_message(db, from_number, not_pet_errors[0])

    if success_count == 0 and fail_count > 0:
        # Entire batch failed — one error message.
        dashboard_link = _get_dashboard_link(db, pet)
        msg = (
            f"Extraction could not process the below documents for *{pet.name}*.\n\n"
        )
        if failed_doc_names:
            for name in failed_doc_names:
                msg += f"  - {name}\n"
            msg += "\n"
        msg += "You can update records manually via the dashboard."
        if dashboard_link:
            msg += f"\n{dashboard_link}"
        await send_text_message(db, from_number, msg)
        return

    # Aggregate results from all successful extractions.
    total_extracted = sum(r.get("items_extracted", 0) for r in all_results)
    total_processed = sum(r.get("items_processed", 0) for r in all_results)

    if total_extracted == 0 and success_count > 0:
        # All docs processed successfully but no preventive items found.
        dashboard_link = _get_dashboard_link(db, pet)
        msg = (
            f"Processed {success_count} document(s) for *{pet.name}*, "
            f"but no preventive health items were found.\n\n"
            f"These may be lab reports or prescriptions without preventive items. "
            f"You can update records manually from the dashboard."
        )
        if fail_count > 0 and failed_doc_names:
            msg += f"\n\n{fail_count} document(s) failed:\n"
            for name in failed_doc_names:
                msg += f"  - {name}\n"
        if dashboard_link:
            msg += f"\n{dashboard_link}"
        await send_text_message(db, from_number, msg)
        return

    # At least some items were found — show detailed summary.
    # Pick the last successful result with items for the detailed view.
    best_result = None
    for r in reversed(all_results):
        if r.get("items_processed", 0) > 0:
            best_result = r
            break

    if best_result:
        await _send_extraction_summary(db, user, pet, best_result,
                                        total_processed, fail_count, failed_doc_names)
    else:
        dashboard_link = _get_dashboard_link(db, pet)
        msg = f"Extraction complete for *{pet.name}*: {success_count} processed, {fail_count} failed."
        if dashboard_link:
            msg += f"\n\n{dashboard_link}"
        await send_text_message(db, from_number, msg)


async def _send_extraction_summary(
    db: Session, user, pet, result: dict,
    batch_total_processed: int = 0, batch_fail_count: int = 0,
    failed_doc_names: list[str] | None = None,
) -> None:
    """
    Send a WhatsApp summary after GPT extraction completes.

    Includes:
        - Count of items extracted and processed.
        - List of extracted item names with dates.
        - Any errors or unmatched items.
        - Dashboard link to view updated records.
    """
    from_number = _get_mobile(user)
    extracted = result.get("items_extracted", 0)
    processed = result.get("items_processed", 0)
    errors = result.get("errors", [])
    status = result.get("status", "failed")
    doctor_name = result.get("doctor_name")
    clinic_name = result.get("clinic_name")
    vaccination_details = result.get("vaccination_details", [])

    if status == "failed":
        # Check for pet name mismatch — show a specific, clear message.
        pet_name_errors = [e for e in errors if "Pet name mismatch" in e]
        if pet_name_errors:
            await send_text_message(db, from_number, pet_name_errors[0])
            return

        dashboard_link = _get_dashboard_link(db, pet)
        msg = (
            f"Document saved but extraction encountered an issue. "
            f"You can update details manually via the dashboard."
        )
        if dashboard_link:
            msg += f"\n\nView *{pet.name}'s Dashboard*:\n{dashboard_link}"
        await send_text_message(db, from_number, msg)
        return

    if extracted == 0:
        await send_text_message(
            db, from_number,
            f"No preventive health items were found in {pet.name}'s document.\n\n"
            f"If this looks wrong, you can update records manually from the dashboard.",
        )
        return

    # Build extraction details from the preventive records in DB.
    # Re-query the latest records to show accurate current state.
    from app.models.preventive_record import PreventiveRecord
    from app.models.preventive_master import PreventiveMaster

    records = (
        db.query(PreventiveRecord, PreventiveMaster)
        .join(PreventiveMaster, PreventiveRecord.preventive_master_id == PreventiveMaster.id)
        .filter(
            PreventiveRecord.pet_id == pet.id,
            PreventiveRecord.last_done_date.isnot(None),
        )
        .order_by(PreventiveRecord.last_done_date.desc())
        .all()
    )

    lines = []
    for record, master in records:
        done_date = record.last_done_date.strftime("%d-%m-%Y") if record.last_done_date else "—"
        next_due = record.next_due_date.strftime("%d-%m-%Y") if record.next_due_date else "—"
        lines.append(f"  • {master.item_name}: done {done_date}, next due {next_due}")

    # Use batch total if available, else single-doc count.
    display_processed = batch_total_processed if batch_total_processed > 0 else processed

    msg = f"Extraction complete for *{pet.name}*!\n\n"
    msg += f"*{display_processed} item(s)* updated.\n"

    if lines:
        msg += f"\n*Health Records:*\n" + "\n".join(lines) + "\n"

    if doctor_name or clinic_name:
        msg += "\n*Extracted Document Details:*\n"
        if doctor_name:
            msg += f"  • Doctor: {doctor_name}\n"
        if clinic_name:
            msg += f"  • Clinic: {clinic_name}\n"

    if vaccination_details:
        msg += "\n*Vaccination Details Found:*\n"
        for detail in vaccination_details[:5]:
            if not isinstance(detail, dict):
                continue
            vaccine_name = detail.get("vaccine_name") or detail.get("vaccine_name_raw") or "Vaccine"
            dose = detail.get("dose")
            batch = detail.get("batch_number")
            admin_by = detail.get("administered_by")
            parts = [str(vaccine_name)]
            if dose:
                parts.append(f"dose {dose}")
            if batch:
                parts.append(f"batch {batch}")
            if admin_by:
                parts.append(f"by {admin_by}")
            msg += "  • " + ", ".join(parts) + "\n"

    if errors:
        unmatched = [e.replace("No match for item: ", "") for e in errors if "No match" in e]
        if unmatched:
            msg += f"\nCould not map these document terms to tracked preventive items: {', '.join(unmatched)}\n"
            msg += "(Usually this means lab-only or non-preventive terms; no preventive record was updated for them.)\n"

    # Include per-document failure details from the batch.
    if batch_fail_count > 0 and failed_doc_names:
        msg += f"\n{batch_fail_count} document(s) could not be processed:\n"
        for name in failed_doc_names:
            msg += f"  - {name}\n"

    dashboard_link = _get_dashboard_link(db, pet)
    if dashboard_link:
        msg += f"\nView *{pet.name}'s Dashboard*:\n{dashboard_link}"

    await send_text_message(db, from_number, msg)


def _mime_to_ext(mime_type: str) -> str:
    """Convert MIME type to file extension."""
    return {"image/jpeg": "jpg", "image/png": "png", "application/pdf": "pdf"}.get(
        mime_type, "bin"
    )
