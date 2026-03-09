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

import asyncio
import logging
import time
from collections import OrderedDict
from fastapi import APIRouter, Request, HTTPException, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
from app.config import settings
from app.database import get_db
from app.core.security import verify_webhook_signature
from app.core.log_sanitizer import mask_phone, sanitize_payload
from app.core.rate_limiter import rate_limiter
from app.models.message_log import MessageLog


logger = logging.getLogger(__name__)

# --- Message deduplication cache ---
# Meta may deliver the same webhook multiple times (retries, network issues).
# We track recently seen message IDs to avoid processing duplicates.
# Using OrderedDict for efficient LRU eviction.
_DEDUP_CACHE: OrderedDict[str, float] = OrderedDict()
_DEDUP_MAX_SIZE = 2000
_DEDUP_TTL_SECONDS = 3600  # 1 hour — Meta may retry webhooks for hours after failures


def _is_duplicate_message(message_id: str) -> bool:
    """
    Check if a message ID was already processed recently.

    Returns True if duplicate (should skip), False if new (should process).
    """
    if not message_id:
        return False

    now = time.time()

    # Evict expired entries from the front of the OrderedDict.
    while _DEDUP_CACHE:
        oldest_key, oldest_time = next(iter(_DEDUP_CACHE.items()))
        if now - oldest_time > _DEDUP_TTL_SECONDS:
            _DEDUP_CACHE.pop(oldest_key)
        else:
            break

    if message_id in _DEDUP_CACHE:
        logger.info("Duplicate message_id %s — skipping.", message_id)
        return True

    _DEDUP_CACHE[message_id] = now

    # Cap cache size.
    if len(_DEDUP_CACHE) > _DEDUP_MAX_SIZE:
        _DEDUP_CACHE.popitem(last=False)

    return False

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
        # Meta expects the challenge echoed back as plain text integer,
        # not JSON-serialized. Use PlainTextResponse to avoid quotes.
        return PlainTextResponse(content=hub_challenge or "")

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

    # --- Step 4: Dedup + Log + Forward ---
    # Only process if we have an actual message (not a status update).
    if message_data.get("has_message"):
        # Deduplicate — Meta may deliver the same webhook multiple times.
        message_id = message_data.get("message_id")

        # Fast path: in-memory cache catches most retries without a DB query.
        if _is_duplicate_message(message_id):
            return {"status": "ok"}

        # Slow path: DB-backed dedup survives server restarts.
        # Checks message_logs.wamid (unique index) for previously processed messages.
        # FAIL-CLOSED: If we can't verify a message is new, reject it.
        # A false-negative (dropping a legitimate new message) is far less harmful
        # than a false-positive (reprocessing an old message and sending phantom uploads).
        if message_id:
            try:
                existing = db.query(MessageLog.id).filter(
                    MessageLog.wamid == message_id
                ).first()
                if existing:
                    logger.info("DB dedup: message_id %s already processed — skipping.", message_id)
                    return {"status": "ok"}
            except Exception as e:
                logger.error("DB dedup check failed — rejecting message to prevent phantom reprocessing: %s", str(e))
                return {"status": "ok"}

        # Log the incoming message AFTER dedup so duplicates aren't logged twice.
        # The wamid unique constraint acts as a final dedup safety net.
        try:
            log_entry = MessageLog(
                mobile_number=mask_phone(message_data.get("from_number")),
                direction="incoming",
                message_type=message_data.get("type"),
                payload=sanitize_payload(payload),
                wamid=message_id,
            )
            db.add(log_entry)
            db.commit()
        except Exception as e:
            # If insert fails due to unique constraint on wamid, it's a duplicate.
            logger.error("Failed to log incoming message (possible duplicate wamid): %s", str(e))
            try:
                db.rollback()
            except Exception:
                pass
            # If we have a message_id and the insert failed, treat as duplicate
            # to prevent reprocessing on unique constraint violations.
            if message_id:
                logger.info("Treating message %s as duplicate after log insert failure.", message_id)
                return {"status": "ok"}

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

        # Reuse the request-scoped db session to avoid exhausting the
        # connection pool (each get_fresh_session() held a second slot).
        try:
            from app.services.message_router import route_message
            # 55s timeout ensures the webhook returns 200 before Meta's
            # 60s timeout, preventing duplicate webhook deliveries under load.
            await asyncio.wait_for(route_message(db, message_data), timeout=55)
        except asyncio.TimeoutError:
            logger.error(
                "Message routing timed out for %s", mask_phone(from_number),
            )
            try:
                from app.services.whatsapp_sender import send_text_message
                await send_text_message(
                    db, from_number,
                    "Your request is taking longer than expected. "
                    "Please try again in a moment.",
                )
            except Exception:
                pass
        except Exception as e:
            # Service layer failure must never prevent 200 OK response.
            logger.error(
                "Error routing message from %s: %s",
                mask_phone(from_number),
                str(e),
                exc_info=True,
            )
            try:
                db.rollback()
            except Exception:
                pass
            # Always attempt to send an error message so the user is never
            # left without a response when the backend crashes.
            try:
                from app.services.whatsapp_sender import send_text_message
                await send_text_message(
                    db, from_number,
                    "We're experiencing a temporary issue. "
                    "Please try again in a few minutes.",
                )
            except Exception:
                logger.error(
                    "Failed to send error message to %s after routing failure",
                    mask_phone(from_number),
                )

    else:
        # Log non-message payloads (status updates, etc.) without dedup.
        try:
            log_entry = MessageLog(
                mobile_number=mask_phone(message_data.get("from_number")),
                direction="incoming",
                message_type=message_data.get("type"),
                payload=sanitize_payload(payload),
            )
            db.add(log_entry)
            db.commit()
        except Exception as e:
            logger.error("Failed to log non-message payload: %s", str(e))
            try:
                db.rollback()
            except Exception:
                pass

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
        "filename": None,
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
        # Image attachment — extract media ID, MIME type, and caption.
        image_obj = message.get("image", {})
        result["media_id"] = image_obj.get("id")
        result["mime_type"] = image_obj.get("mime_type")
        result["caption"] = image_obj.get("caption")

    elif msg_type == "document":
        # Document attachment — extract media ID, MIME type, filename, and caption.
        doc_obj = message.get("document", {})
        result["media_id"] = doc_obj.get("id")
        result["mime_type"] = doc_obj.get("mime_type")
        result["filename"] = doc_obj.get("filename")
        result["caption"] = doc_obj.get("caption")

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
