"""
PetCircle Phase 1 — Security Utilities

Provides webhook signature verification and admin authentication.

Security model:
    - WhatsApp webhook: validates X-Hub-Signature-256 header using HMAC-SHA256
    - Admin endpoints: validates X-ADMIN-KEY header against ADMIN_SECRET_KEY
    - Dashboard: token-based access (validated in dashboard router)

All security checks are structural — they run before any business logic.
"""

import hmac
import hashlib
import logging
from fastapi import Request, HTTPException, Header
from app.config import settings


logger = logging.getLogger(__name__)


def verify_webhook_signature(payload: bytes, signature_header: str) -> bool:
    """
    Verify the X-Hub-Signature-256 header from Meta's WhatsApp webhook.

    Meta signs every webhook payload with HMAC-SHA256 using the app secret.
    This function recomputes the signature and compares it to prevent
    tampered or forged webhook deliveries.

    Args:
        payload: The raw request body bytes.
        signature_header: The value of the X-Hub-Signature-256 header,
            in the format "sha256=<hex_digest>".

    Returns:
        True if the signature is valid, False otherwise.
    """
    if not signature_header:
        logger.warning("Webhook signature header missing.")
        return False

    # Meta prefixes the signature with "sha256="
    if not signature_header.startswith("sha256="):
        logger.warning("Webhook signature header has invalid format.")
        return False

    expected_signature = signature_header[7:]  # Strip "sha256=" prefix

    # Compute HMAC-SHA256 using the WhatsApp app secret.
    # WHATSAPP_APP_SECRET is the shared secret Meta uses to sign webhook payloads.
    computed = hmac.new(
        key=settings.WHATSAPP_APP_SECRET.encode("utf-8"),
        msg=payload,
        digestmod=hashlib.sha256,
    ).hexdigest()

    # Constant-time comparison to prevent timing attacks.
    is_valid = hmac.compare_digest(computed, expected_signature)

    if not is_valid:
        logger.warning("Webhook signature verification failed.")

    return is_valid


async def validate_admin_key(x_admin_key: str = Header(None, alias="X-ADMIN-KEY")) -> str:
    """
    FastAPI dependency that validates the admin API key.

    Every admin endpoint must include this dependency to enforce
    authentication. The X-ADMIN-KEY header is compared against
    ADMIN_SECRET_KEY from environment configuration.

    Args:
        x_admin_key: The value of the X-ADMIN-KEY request header.

    Returns:
        The validated admin key string (for downstream use if needed).

    Raises:
        HTTPException 403: If the key is missing or does not match.
    """
    if not x_admin_key or x_admin_key != settings.ADMIN_SECRET_KEY:
        logger.warning("Admin authentication failed — invalid X-ADMIN-KEY.")
        raise HTTPException(
            status_code=403,
            detail="Forbidden — invalid admin key.",
        )
    return x_admin_key
