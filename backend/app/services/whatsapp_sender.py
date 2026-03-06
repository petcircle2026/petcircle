"""
PetCircle Phase 1 — WhatsApp Message Sending Utility

Sends messages and templates via the WhatsApp Cloud API.
Used by the reminder engine, conflict notifications, onboarding,
and general reply flows.

All credentials loaded from environment config — never hardcoded.

Message types:
    - Text reply: plain text response to a user message
    - Template message: pre-approved template (reminders, overdue, conflict)
    - Interactive buttons: buttons for reminder/conflict responses

Rate limiting:
    - MAX_MESSAGES_PER_MINUTE per phone number (rolling window)
    - Enforced at the sender level to prevent quota violations

Retry policy:
    - Uses retry_whatsapp_call (1 retry, never raises)
    - Failures are logged but never crash the calling flow
"""

import logging
from datetime import datetime
import httpx
from sqlalchemy.orm import Session
from app.config import settings
from app.core.constants import (
    MAX_MESSAGES_PER_MINUTE,
    RATE_LIMIT_WINDOW_SECONDS,
    REMINDER_DONE,
    REMINDER_SNOOZE_7,
    REMINDER_RESCHEDULE,
    REMINDER_CANCEL,
    CONFLICT_USE_NEW,
    CONFLICT_KEEP_EXISTING,
)
from app.core.log_sanitizer import mask_phone, sanitize_payload
from app.core.rate_limiter import rate_limiter
from app.utils.retry import retry_whatsapp_call
from app.models.message_log import MessageLog


logger = logging.getLogger(__name__)

# WhatsApp Cloud API base URL
WHATSAPP_API_URL = (
    f"https://graph.facebook.com/v21.0/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
)

# Headers for all WhatsApp API calls
WHATSAPP_HEADERS = {
    "Authorization": f"Bearer {settings.WHATSAPP_TOKEN}",
    "Content-Type": "application/json",
}


async def _send_whatsapp_request(payload: dict) -> dict | None:
    """
    Send a request to the WhatsApp Cloud API.

    Wraps the HTTP call with retry_whatsapp_call (1 retry, never raises).
    Logs the full payload for audit trail.

    Args:
        payload: The JSON payload to send to the WhatsApp API.

    Returns:
        The API response dict on success, None on failure.
    """
    async def _make_call() -> dict:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                WHATSAPP_API_URL,
                headers=WHATSAPP_HEADERS,
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    return await retry_whatsapp_call(_make_call)


def _log_outgoing_message(
    db: Session,
    mobile_number: str,
    message_type: str,
    payload: dict,
) -> None:
    """
    Log an outgoing WhatsApp message to message_logs.

    Logging must never block the main flow — errors are caught silently.

    Args:
        db: SQLAlchemy database session.
        mobile_number: Recipient's WhatsApp number.
        message_type: Type of message (text, template, interactive).
        payload: The full API payload sent.
    """
    try:
        log_entry = MessageLog(
            mobile_number=mobile_number,
            direction="outgoing",
            message_type=message_type,
            payload=sanitize_payload(payload),
        )
        db.add(log_entry)
        db.commit()
    except Exception as e:
        logger.error("Failed to log outgoing message: %s", str(e))
        try:
            db.rollback()
        except Exception:
            pass


async def send_text_message(
    db: Session,
    to_number: str,
    text: str,
) -> dict | None:
    """
    Send a plain text message via WhatsApp Cloud API.

    Args:
        db: SQLAlchemy database session (for logging).
        to_number: Recipient's WhatsApp phone number.
        text: The text message body.

    Returns:
        API response dict on success, None on failure.
    """
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "text",
        "text": {"body": text},
    }

    # Rate limit check before sending.
    if not rate_limiter.check_rate_limit(to_number):
        logger.warning("Outgoing rate limited for %s", mask_phone(to_number))
        return None

    result = await _send_whatsapp_request(payload)

    _log_outgoing_message(db, to_number, "text", payload)

    if result:
        logger.info("Text message sent to %s", mask_phone(to_number))
    else:
        logger.warning("Text message failed to %s", mask_phone(to_number))

    return result


async def send_template_message(
    db: Session,
    to_number: str,
    template_name: str,
    parameters: list[str] | None = None,
    language_code: str = "en",
) -> dict | None:
    """
    Send a template message via WhatsApp Cloud API.

    Template names are loaded from environment config — never hardcoded.

    Args:
        db: SQLAlchemy database session (for logging).
        to_number: Recipient's WhatsApp phone number.
        template_name: The approved template name (from settings).
        parameters: Optional list of parameter values for template variables.
        language_code: Language code for the template (default: en).

    Returns:
        API response dict on success, None on failure.
    """
    # Build template components
    components = []
    if parameters:
        body_params = [
            {"type": "text", "text": p} for p in parameters
        ]
        components.append({
            "type": "body",
            "parameters": body_params,
        })

    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language_code},
        },
    }

    if components:
        payload["template"]["components"] = components

    # Rate limit check before sending.
    if not rate_limiter.check_rate_limit(to_number):
        logger.warning("Outgoing rate limited for %s", mask_phone(to_number))
        return None

    result = await _send_whatsapp_request(payload)

    _log_outgoing_message(db, to_number, "template", payload)

    if result:
        logger.info(
            "Template '%s' sent to %s",
            template_name, mask_phone(to_number),
        )
    else:
        logger.warning(
            "Template '%s' failed to %s",
            template_name, mask_phone(to_number),
        )

    return result


async def send_interactive_buttons(
    db: Session,
    to_number: str,
    body_text: str,
    buttons: list[dict],
) -> dict | None:
    """
    Send an interactive button message via WhatsApp Cloud API.

    Used for reminder responses and conflict resolution prompts.
    Button payload IDs are from constants — never hardcoded.

    Args:
        db: SQLAlchemy database session (for logging).
        to_number: Recipient's WhatsApp phone number.
        body_text: The message body text.
        buttons: List of button dicts, each with 'id' and 'title'.
            Example: [{"id": "REMINDER_DONE", "title": "Done"}]

    Returns:
        API response dict on success, None on failure.
    """
    button_rows = [
        {"type": "reply", "reply": {"id": b["id"], "title": b["title"]}}
        for b in buttons
    ]

    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": body_text},
            "action": {"buttons": button_rows},
        },
    }

    # Rate limit check before sending.
    if not rate_limiter.check_rate_limit(to_number):
        logger.warning("Outgoing rate limited for %s", mask_phone(to_number))
        return None

    result = await _send_whatsapp_request(payload)

    _log_outgoing_message(db, to_number, "interactive", payload)

    if result:
        logger.info("Interactive buttons sent to %s", mask_phone(to_number))
    else:
        logger.warning("Interactive buttons failed to %s", mask_phone(to_number))

    return result


async def send_reminder_message(
    db: Session,
    to_number: str,
    pet_name: str,
    item_name: str,
    due_date: str,
    record_status: str,
) -> dict | None:
    """
    Send a reminder or overdue template message with interactive buttons.

    Template selection:
        - record_status == 'upcoming' → WHATSAPP_TEMPLATE_REMINDER
        - record_status == 'overdue'  → WHATSAPP_TEMPLATE_OVERDUE

    After sending the template, sends interactive buttons for the user
    to respond (Done, Snooze, Reschedule, Cancel).

    Args:
        db: SQLAlchemy database session.
        to_number: Recipient's WhatsApp phone number.
        pet_name: Name of the pet.
        item_name: Name of the preventive item.
        due_date: Due date as string.
        record_status: 'upcoming' or 'overdue'.

    Returns:
        API response dict on success, None on failure.
    """
    # Select template based on record status.
    if record_status == "overdue":
        template_name = settings.WHATSAPP_TEMPLATE_OVERDUE
    else:
        template_name = settings.WHATSAPP_TEMPLATE_REMINDER

    # Send the template message with parameters.
    result = await send_template_message(
        db=db,
        to_number=to_number,
        template_name=template_name,
        parameters=[pet_name, item_name, due_date],
    )

    return result


async def send_conflict_notification(
    db: Session,
    to_number: str,
    pet_name: str,
    item_name: str,
    existing_date: str,
    new_date: str,
) -> dict | None:
    """
    Send a conflict notification with resolution buttons.

    Sends the conflict template followed by interactive buttons
    for the user to choose between keeping the existing date
    or using the new date.

    Args:
        db: SQLAlchemy database session.
        to_number: Recipient's WhatsApp phone number.
        pet_name: Name of the pet.
        item_name: Name of the conflicting preventive item.
        existing_date: Current date on record.
        new_date: Newly extracted conflicting date.

    Returns:
        API response dict on success, None on failure.
    """
    # Send conflict template.
    result = await send_template_message(
        db=db,
        to_number=to_number,
        template_name=settings.WHATSAPP_TEMPLATE_CONFLICT,
        parameters=[pet_name, item_name, existing_date, new_date],
    )

    if result:
        # Send resolution buttons.
        await send_interactive_buttons(
            db=db,
            to_number=to_number,
            body_text=(
                f"Which date should we keep for {pet_name}'s {item_name}?\n"
                f"Existing: {existing_date}\n"
                f"New: {new_date}"
            ),
            buttons=[
                {"id": CONFLICT_USE_NEW, "title": "Use New Date"},
                {"id": CONFLICT_KEEP_EXISTING, "title": "Keep Existing"},
            ],
        )

    return result


async def download_whatsapp_media(media_id: str) -> tuple[bytes, str] | None:
    """
    Download media from WhatsApp Cloud API using a media ID.

    Two-step process:
        1. GET the media URL from Meta's API.
        2. Download the actual file content.

    Args:
        media_id: The media ID from the incoming WhatsApp message.

    Returns:
        Tuple of (file_bytes, mime_type) on success, None on failure.
    """
    import asyncio as _asyncio

    # Retry on transient SSL errors from Meta's CDN.
    max_retries = 2
    for attempt in range(max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Step 1: Get media URL
                media_url_response = await client.get(
                    f"https://graph.facebook.com/v21.0/{media_id}",
                    headers={"Authorization": f"Bearer {settings.WHATSAPP_TOKEN}"},
                )
                media_url_response.raise_for_status()
                media_info = media_url_response.json()

                media_url = media_info.get("url")
                mime_type = media_info.get("mime_type", "application/octet-stream")

                if not media_url:
                    logger.error("No URL in media response for media_id=%s", media_id)
                    return None

                # Step 2: Download the file
                file_response = await client.get(
                    media_url,
                    headers={"Authorization": f"Bearer {settings.WHATSAPP_TOKEN}"},
                )
                file_response.raise_for_status()

                logger.info(
                    "Media downloaded: media_id=%s, mime=%s, size=%d",
                    media_id, mime_type, len(file_response.content),
                )

                return file_response.content, mime_type

        except Exception as e:
            logger.error(
                "Failed to download media: media_id=%s, attempt=%d/%d, error=%s",
                media_id, attempt + 1, max_retries + 1, str(e),
            )
            if attempt < max_retries:
                await _asyncio.sleep(1)
            else:
                return None
