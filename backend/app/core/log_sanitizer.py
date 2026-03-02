"""
PetCircle Phase 1 — Log Sanitizer

Masks PII (phone numbers, tokens) and sanitizes message payloads
before logging or returning in admin API responses.

Prevents sensitive data from appearing in log files or error outputs.

Masking rules:
    - Phone numbers: show first 2 + last 4 digits (e.g., "91****1234")
    - Tokens: show first 4 characters only (e.g., "abc1****")
    - Payloads: strip message content, mask phone numbers, keep metadata
"""

import copy


def mask_phone(number: str) -> str:
    """
    Mask a phone number for safe logging.

    Shows first 2 digits (country code) and last 4 digits.
    Example: "919876543210" → "91****3210"

    Args:
        number: The full phone number string.

    Returns:
        Masked phone number, or "****" if too short.
    """
    if not number:
        return "****"
    number = str(number)
    if len(number) <= 6:
        return "****"
    return f"{number[:2]}****{number[-4:]}"


def mask_token(token: str) -> str:
    """
    Mask a token/secret for safe logging.

    Shows only the first 4 characters.
    Example: "abc123def456" → "abc1****"

    Args:
        token: The token or secret string.

    Returns:
        Masked token string.
    """
    if not token:
        return "****"
    token = str(token)
    if len(token) <= 4:
        return "****"
    return f"{token[:4]}****"


def sanitize_payload(payload: dict) -> dict:
    """
    Sanitize a WhatsApp message payload for safe storage/logging.

    Strips or masks sensitive fields while preserving metadata:
        - "from" (phone number): masked
        - "wa_id": masked
        - "text.body": truncated to first 20 chars + "..."
        - Contact phone numbers: masked

    Preserves: type, timestamp, id, status, template names.

    Args:
        payload: The raw WhatsApp API payload dict.

    Returns:
        A deep copy with sensitive fields masked/truncated.
    """
    if not payload:
        return payload

    sanitized = copy.deepcopy(payload)

    # Sanitize entries → changes → value → messages
    for entry in sanitized.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})

            # Mask contact phone numbers
            for contact in value.get("contacts", []):
                if "wa_id" in contact:
                    contact["wa_id"] = mask_phone(contact["wa_id"])
                profile = contact.get("profile", {})
                # Keep profile name — not PII-sensitive at this level

            # Sanitize messages
            for message in value.get("messages", []):
                if "from" in message:
                    message["from"] = mask_phone(message["from"])

                # Truncate text body
                text_obj = message.get("text", {})
                if "body" in text_obj:
                    body = text_obj["body"]
                    if len(body) > 20:
                        text_obj["body"] = body[:20] + "..."

    # Sanitize outgoing payloads (sent via WhatsApp sender)
    if "to" in sanitized:
        sanitized["to"] = mask_phone(sanitized.get("to", ""))

    # Truncate outgoing text body
    if "text" in sanitized and isinstance(sanitized["text"], dict):
        body = sanitized["text"].get("body", "")
        if len(body) > 20:
            sanitized["text"]["body"] = body[:20] + "..."

    return sanitized
