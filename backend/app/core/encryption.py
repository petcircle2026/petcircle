"""
PetCircle Phase 1 — Field-Level PII Encryption

Provides symmetric encryption for sensitive user data (mobile numbers,
emails, pincodes) using Fernet (AES-128-CBC with HMAC-SHA256).

Encryption strategy:
    - encrypt_field / decrypt_field: Non-deterministic Fernet encryption
      for storing PII. Same plaintext produces different ciphertext each time.
    - hash_field: Deterministic SHA-256 hash for indexed lookups
      (e.g., finding a user by mobile number without decrypting all rows).

Usage:
    - On write: encrypt PII fields, store hash for lookup columns.
    - On read: decrypt PII fields for display/processing.
    - For lookups: query by hash column instead of encrypted column.

The ENCRYPTION_KEY must be a valid Fernet key (base64-encoded 32 bytes).
Generate one with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken
from app.config import settings

logger = logging.getLogger(__name__)

# Initialize Fernet cipher with the application encryption key.
_fernet = Fernet(settings.ENCRYPTION_KEY.encode("utf-8"))


def encrypt_field(value: str) -> str:
    """
    Encrypt a plaintext string using Fernet symmetric encryption.

    Each call produces a different ciphertext (non-deterministic)
    due to Fernet's built-in timestamp and IV.

    Args:
        value: The plaintext string to encrypt.

    Returns:
        Base64-encoded ciphertext string.
    """
    if not value:
        return value
    return _fernet.encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_field(token: str) -> str:
    """
    Decrypt a Fernet-encrypted string back to plaintext.

    Args:
        token: The base64-encoded ciphertext string.

    Returns:
        The original plaintext string.

    Raises:
        InvalidToken: If the token is invalid or corrupted.
    """
    if not token:
        return token
    try:
        return _fernet.decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        logger.error("Failed to decrypt field — invalid token.")
        raise


def hash_field(value: str) -> str:
    """
    Produce a deterministic SHA-256 hash for indexed lookups.

    Used to find records by sensitive fields (e.g., mobile number)
    without needing to decrypt every row. The hash is not reversible.

    Args:
        value: The plaintext string to hash.

    Returns:
        Hex-encoded SHA-256 hash string (64 characters).
    """
    if not value:
        return value
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
