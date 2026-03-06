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

import logging
from sqlalchemy.orm import Session
from app.core.encryption import decrypt_field
from app.core.log_sanitizer import mask_phone
from app.core.constants import (
    REMINDER_DONE,
    REMINDER_SNOOZE_7,
    REMINDER_RESCHEDULE,
    REMINDER_CANCEL,
    CONFLICT_USE_NEW,
    CONFLICT_KEEP_EXISTING,
    MAX_PETS_PER_USER,
)
from app.services.onboarding import (
    get_or_create_user,
    create_pending_user,
    handle_onboarding_step,
)
from app.services.whatsapp_sender import (
    send_text_message,
    download_whatsapp_media,
)
from app.models.pet import Pet
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

    try:
        # --- Step 1: Look up or create user ---
        user, is_existing = get_or_create_user(db, from_number)

        if not is_existing:
            # Brand new user — create pending record, send welcome
            user = create_pending_user(db, from_number)
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

        # Attach plaintext number for downstream sending.
        # user.mobile_number is encrypted in DB; from_number is plaintext from webhook.
        user._plaintext_mobile = from_number

        # --- Step 2: Check if user is still onboarding ---
        if user.onboarding_state and user.onboarding_state != "complete":
            text = (message_data.get("text") or "").strip()
            if not text:
                await send_text_message(
                    db, from_number,
                    "Please send a text message to continue setup.",
                )
                return
            await handle_onboarding_step(db, user, text, send_text_message)
            return

        # --- Step 3: User is fully onboarded — route by message type ---
        if msg_type == "button":
            await _handle_button(db, user, message_data)

        elif msg_type in ("image", "document"):
            await _handle_media(db, user, message_data)

        elif msg_type == "text":
            await _handle_text(db, user, message_data)

        else:
            logger.info("Unhandled message type '%s' from %s", msg_type, mask_phone(from_number))

    except Exception as e:
        logger.error("Error routing message from %s: %s", mask_phone(from_number), str(e))
        try:
            await send_text_message(
                db, from_number,
                "Sorry, something went wrong. Please try again.",
            )
        except Exception:
            pass


async def _handle_text(db: Session, user, message_data: dict) -> None:
    """
    Handle a text message from a fully onboarded user.

    Routing:
        - "add pet" / "new pet" → start new pet onboarding
        - "dashboard" / "link" → send dashboard links
        - anything else → query engine
    """
    text = (message_data.get("text") or "").strip()
    text_lower = text.lower()
    from_number = _get_mobile(user)

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

    # "dashboard" command
    if text_lower in ("dashboard", "link", "my dashboard"):
        await _send_dashboard_links(db, user)
        return

    # General query — route to GPT query engine
    await _handle_query(db, user, text)


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

    # Find user's pets
    pets = db.query(Pet).filter(
        Pet.user_id == user.id, Pet.is_deleted == False
    ).all()
    pet_ids = [p.id for p in pets]

    if not pet_ids:
        await send_text_message(db, from_number, "No pets found.")
        return

    # Find the latest sent reminder
    reminder = (
        db.query(Reminder)
        .join(PreventiveRecord, Reminder.preventive_record_id == PreventiveRecord.id)
        .filter(
            PreventiveRecord.pet_id.in_(pet_ids),
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

    pets = db.query(Pet).filter(
        Pet.user_id == user.id, Pet.is_deleted == False
    ).all()
    pet_ids = [p.id for p in pets]

    if not pet_ids:
        await send_text_message(db, from_number, "No pets found.")
        return

    conflict = (
        db.query(ConflictFlag)
        .join(PreventiveRecord, ConflictFlag.preventive_record_id == PreventiveRecord.id)
        .filter(
            PreventiveRecord.pet_id.in_(pet_ids),
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
    """Handle image or document uploads — download, store, extract."""
    from app.services.document_upload import process_document_upload
    from app.services.gpt_extraction import extract_and_process_document

    from_number = _get_mobile(user)
    media_id = message_data.get("media_id")

    if not media_id:
        await send_text_message(db, from_number, "Couldn't process that file. Please try again.")
        return

    # Find user's most recent active pet
    pet = (
        db.query(Pet)
        .filter(Pet.user_id == user.id, Pet.is_deleted == False)
        .order_by(Pet.created_at.desc())
        .first()
    )

    if not pet:
        await send_text_message(db, from_number, "Please register a pet first.")
        return

    # Download media from WhatsApp
    media_result = await download_whatsapp_media(media_id)
    if not media_result:
        await send_text_message(db, from_number, "Failed to download the file. Please try again.")
        return

    file_content, detected_mime = media_result

    try:
        filename = f"{media_id}.{_mime_to_ext(detected_mime)}"
        document = await process_document_upload(
            db=db,
            pet_id=pet.id,
            user_id=user.id,
            filename=filename,
            file_content=file_content,
            mime_type=detected_mime,
        )

        await send_text_message(
            db, from_number,
            f"Document received for {pet.name}! Extracting health data...",
        )

        # Trigger GPT extraction
        try:
            document_text = f"[Uploaded file: {filename}, type: {detected_mime}]"
            await extract_and_process_document(db, document.id, document_text)
            await send_text_message(
                db, from_number,
                f"Extraction complete for {pet.name}'s document!",
            )
        except Exception as e:
            logger.error("GPT extraction failed: %s", str(e))
            await send_text_message(
                db, from_number,
                "Document saved but extraction encountered an issue. "
                "You can update details manually via the dashboard.",
            )

    except ValueError as e:
        await send_text_message(db, from_number, str(e))
    except RuntimeError:
        await send_text_message(db, from_number, "Upload failed. Please try again later.")


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
        result = await answer_pet_question(db, pet.id, text)
        answer = result.get("answer", "Sorry, I couldn't find an answer.")
        await send_text_message(db, from_number, answer)
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

    messages = []
    for pet in pets:
        token_record = (
            db.query(DashboardToken)
            .filter(DashboardToken.pet_id == pet.id, DashboardToken.revoked == False)
            .first()
        )

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

    await send_text_message(
        db, from_number,
        "Your pet dashboards:\n\n" + "\n".join(messages),
    )


def _mime_to_ext(mime_type: str) -> str:
    """Convert MIME type to file extension."""
    return {"image/jpeg": "jpg", "image/png": "png", "application/pdf": "pdf"}.get(
        mime_type, "bin"
    )
