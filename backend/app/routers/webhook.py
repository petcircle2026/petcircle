"""
PetCircle Phase 1 — WhatsApp Webhook Router (Module 4)

Route: /webhook/whatsapp

Handles incoming WhatsApp events from Meta's Cloud API.
This layer does ONLY:
    1. Signature verification (GET: token match, POST: HMAC-SHA256)
    2. Payload parsing (robust nested dictionary extraction)
    3. Message type detection (text, image, document, button)
    4. Logging ALL incoming payloads to message_logs
    5. Passing structured objects to the service layer

NO business logic lives here. No onboarding, no preventive logic,
no GPT calls. Just parsing, validation, and forwarding.
"""

import logging
from fastapi import APIRouter, Request, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from app.config import settings
from app.database import get_db
from app.core.security import verify_webhook_signature
from app.core.log_sanitizer import mask_phone, sanitize_payload
from app.core.rate_limiter import rate_limiter
from app.models.message_log import MessageLog


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["webhook"])


@router.get("/whatsapp")
async def verify_whatsapp_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    """
    WhatsApp webhook verification endpoint (GET).

    Meta sends a GET request during webhook registration to verify
    ownership. We must:
        1. Check that hub.mode is "subscribe"
        2. Verify hub.verify_token matches our WHATSAPP_VERIFY_TOKEN
        3. Return hub.challenge as the response body

    If verification fails, return 403 to reject the registration.
    """
    if hub_mode == "subscribe" and hub_verify_token == settings.WHATSAPP_VERIFY_TOKEN:
        logger.info("WhatsApp webhook verification succeeded.")
        # Meta expects the challenge echoed back as plain text.
        # It may be numeric or alphanumeric — return as-is.
        return hub_challenge or ""

    logger.warning("WhatsApp webhook verification failed — token mismatch.")
    raise HTTPException(status_code=403, detail="Verification failed.")


@router.post("/whatsapp")
async def handle_whatsapp_message(request: Request, db: Session = Depends(get_db)):
    """
    WhatsApp webhook message handler (POST).

    Receives all incoming WhatsApp events from Meta's Cloud API.
    Processing steps:
        1. Read raw body and verify X-Hub-Signature-256
        2. Parse JSON payload
        3. Extract message details using robust nested dict extraction
        4. Detect message type (text, image, document, button)
        5. Log the full payload to message_logs
        6. Pass structured message object to service layer

    Returns 200 OK immediately — Meta requires fast acknowledgment.
    Heavy processing (GPT, DB writes) is handled downstream.
    """
    # --- Step 1: Signature verification ---
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")

    if not verify_webhook_signature(body, signature):
        logger.warning("Rejected webhook — invalid signature.")
        raise HTTPException(status_code=403, detail="Invalid signature.")

    # --- Step 2: Parse JSON payload ---
    try:
        payload = await request.json()
    except Exception:
        logger.error("Failed to parse webhook JSON payload.")
        raise HTTPException(status_code=400, detail="Invalid JSON.")

    # --- Step 3: Extract message details ---
    # Meta's webhook payload is deeply nested. We extract safely
    # to handle partial payloads (e.g., status updates without messages).
    message_data = _extract_message_data(payload)

    # --- Step 4: Log ALL incoming payloads ---
    # Logging must not block the flow — wrapped in try/except.
    # Payloads are sanitized before storage to strip PII.
    try:
        log_entry = MessageLog(
            mobile_number=message_data.get("from_number"),
            direction="incoming",
            message_type=message_data.get("type"),
            payload=sanitize_payload(payload),
        )
        db.add(log_entry)
        db.commit()
    except Exception as e:
        # Logging failure must never block message processing.
        logger.error("Failed to log incoming message: %s", str(e))
        db.rollback()

    # --- Step 5: Forward to service layer ---
    # Only process if we have an actual message (not a status update).
    if message_data.get("has_message"):
        from_number = message_data.get("from_number", "unknown")

        # Rate limit check — reject if this phone exceeds the limit.
        if from_number != "unknown" and not rate_limiter.check_rate_limit(from_number):
            logger.warning("Rate limited: phone=%s", mask_phone(from_number))
            return {"status": "ok"}

        logger.info(
            "Received %s message from %s",
            message_data.get("type", "unknown"),
            mask_phone(from_number),
        )

        # Route message to the appropriate service handler.
        # Processing is done inline (not queued) in Phase 1.
        # Errors are caught inside the router — never crashes the webhook.
        try:
            from app.services.message_router import route_message
            await route_message(db, message_data)
        except Exception as e:
            # Service layer failure must never prevent 200 OK response.
            logger.error(
                "Service layer error for message from %s: %s",
                mask_phone(from_number),
                str(e),
            )

    # Return 200 OK immediately — Meta requires fast acknowledgment.
    return {"status": "ok"}


def _extract_message_data(payload: dict) -> dict:
    """
    Extract message details from Meta's deeply nested webhook payload.

    Meta's WhatsApp Cloud API sends payloads with this structure:
        entry[0].changes[0].value.messages[0]

    This function safely navigates the nested structure and returns
    a flat dictionary with the relevant fields. If any level is missing,
    it returns safe defaults rather than crashing.

    Detects message types:
        - text: plain text message
        - image: image attachment
        - document: document attachment (PDF, etc.)
        - button: interactive button response (payload ID)

    Args:
        payload: The raw parsed JSON payload from Meta.

    Returns:
        A flat dictionary with keys:
            - has_message: bool — whether this payload contains a message
            - from_number: str — sender's WhatsApp number
            - message_id: str — Meta's message ID
            - type: str — message type (text/image/document/button)
            - text: str — message text (for text messages)
            - media_id: str — media ID (for image/document messages)
            - mime_type: str — MIME type (for image/document messages)
            - button_payload: str — button payload ID (for button messages)
    """
    result = {
        "has_message": False,
        "from_number": None,
        "message_id": None,
        "type": None,
        "text": None,
        "media_id": None,
        "mime_type": None,
        "button_payload": None,
    }

    # Safely navigate nested structure: entry → changes → value
    entries = payload.get("entry", [])
    if not entries:
        return result

    changes = entries[0].get("changes", [])
    if not changes:
        return result

    value = changes[0].get("value", {})

    # Extract contact info (sender's number).
    contacts = value.get("contacts", [])
    if contacts:
        result["from_number"] = contacts[0].get("wa_id")

    # Extract message — may not exist for status updates.
    messages = value.get("messages", [])
    if not messages:
        return result

    message = messages[0]
    result["has_message"] = True
    result["from_number"] = message.get("from", result["from_number"])
    result["message_id"] = message.get("id")
    result["type"] = message.get("type")

    # --- Type-specific extraction ---

    msg_type = result["type"]

    if msg_type == "text":
        # Plain text message.
        text_obj = message.get("text", {})
        result["text"] = text_obj.get("body")

    elif msg_type == "image":
        # Image attachment — extract media ID and MIME type.
        image_obj = message.get("image", {})
        result["media_id"] = image_obj.get("id")
        result["mime_type"] = image_obj.get("mime_type")

    elif msg_type == "document":
        # Document attachment — extract media ID, MIME type, and filename.
        doc_obj = message.get("document", {})
        result["media_id"] = doc_obj.get("id")
        result["mime_type"] = doc_obj.get("mime_type")

    elif msg_type == "button":
        # Interactive button response — extract the payload ID.
        # Payload IDs like REMINDER_DONE, CONFLICT_USE_NEW are defined
        # in constants — never hardcoded in this extraction layer.
        button_obj = message.get("button", {})
        result["button_payload"] = button_obj.get("payload")

    elif msg_type == "interactive":
        # Interactive list/button reply — different structure from simple buttons.
        interactive_obj = message.get("interactive", {})
        button_reply = interactive_obj.get("button_reply", {})
        result["button_payload"] = button_reply.get("id")
        result["type"] = "button"  # Normalize to "button" for downstream processing.

    return result
