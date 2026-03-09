"""
PetCircle Phase 1 — Document Upload Service (Module 7)

Handles file upload validation, Supabase storage, and document record
creation. This is the entry point for the document processing pipeline:

    Upload → Validate → Store → Insert DB record → Trigger extraction

Validation rules:
    - File size: max MAX_UPLOAD_MB (10MB) — from constants.
    - MIME type: must be in ALLOWED_MIME_TYPES (jpeg, png, pdf) — from constants.
    - Daily upload limit: MAX_UPLOADS_PER_PET_PER_DAY (10) — from constants.

Storage:
    - Private Supabase bucket (SUPABASE_BUCKET_NAME from env).
    - Path format: {user_id}/{pet_id}/{filename} — from STORAGE_PATH_TEMPLATE constant.
    - No public URLs — files accessed only through signed URLs.

Rules:
    - All limits from constants.py — no hardcoded values.
    - Bucket name from environment config — never hardcoded.
    - All operations logged.
    - Upload failures do not crash the application.
    - Document record inserted with extraction_status='pending'.
"""

import logging
from datetime import datetime
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.document import Document
from app.models.pet import Pet
from app.core.constants import (
    MAX_UPLOAD_BYTES,
    MAX_UPLOAD_MB,
    MAX_UPLOADS_PER_PET_PER_DAY,
    ALLOWED_MIME_TYPES,
    STORAGE_PATH_TEMPLATE,
)
from app.config import settings
import pytz
from app.utils.date_utils import get_today_ist, IST


logger = logging.getLogger(__name__)

# Cached Supabase client — created once, reused across uploads.
_supabase_client = None


def _get_supabase_client():
    """Return a cached Supabase client instance (created on first call)."""
    global _supabase_client
    if _supabase_client is None:
        from supabase import create_client
        _supabase_client = create_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_SERVICE_ROLE_KEY,
        )
    return _supabase_client


def validate_file_upload(
    file_size: int,
    mime_type: str,
) -> None:
    """
    Validate file size and MIME type before upload.

    Enforces:
        - File size must not exceed MAX_UPLOAD_BYTES (10MB).
        - MIME type must be in ALLOWED_MIME_TYPES (jpeg, png, pdf).

    All limits are read from constants.py — never hardcoded.

    Args:
        file_size: Size of the uploaded file in bytes.
        mime_type: MIME type of the uploaded file.

    Raises:
        ValueError: If file exceeds size limit or MIME type is not allowed.
    """
    # --- Size validation ---
    # MAX_UPLOAD_BYTES is derived from MAX_UPLOAD_MB in constants.
    if file_size > MAX_UPLOAD_BYTES:
        raise ValueError(
            f"File size ({file_size} bytes) exceeds maximum allowed "
            f"({MAX_UPLOAD_MB}MB / {MAX_UPLOAD_BYTES} bytes)."
        )

    # --- MIME type validation ---
    # Only jpeg, png, and pdf are accepted — from ALLOWED_MIME_TYPES constant.
    if mime_type not in ALLOWED_MIME_TYPES:
        raise ValueError(
            f"File type '{mime_type}' is not allowed. "
            f"Accepted types: {', '.join(sorted(ALLOWED_MIME_TYPES))}."
        )


def check_daily_upload_limit(
    db: Session,
    pet_id: UUID,
    pet_name: str | None = None,
) -> None:
    """
    Check if the pet has reached the daily upload limit.

    Enforces MAX_UPLOADS_PER_PET_PER_DAY (10) — from constants.
    Counts documents uploaded today (IST timezone) for this pet.

    Uses IST day boundaries (midnight to midnight IST) instead of comparing
    against func.date(created_at) which would use UTC and be off near midnight.

    Args:
        db: SQLAlchemy database session.
        pet_id: UUID of the pet to check.

    Raises:
        ValueError: If the daily upload limit has been reached.
    """
    from datetime import datetime, timedelta
    # Compute IST day boundaries in UTC for accurate comparison.
    # created_at is stored as UTC, so we need UTC timestamps for IST midnight.
    now_ist = datetime.now(IST)
    ist_midnight = now_ist.replace(hour=0, minute=0, second=0, microsecond=0)
    ist_midnight_utc = ist_midnight.astimezone(pytz.utc).replace(tzinfo=None)
    ist_end_utc = (ist_midnight + timedelta(days=1)).astimezone(pytz.utc).replace(tzinfo=None)

    # Count documents uploaded within today's IST boundaries (converted to UTC).
    # Only count pending or successful documents — failed extractions (e.g.,
    # OpenAI quota exceeded) should not block the user from uploading again.
    today_count = (
        db.query(func.count(Document.id))
        .filter(
            Document.pet_id == pet_id,
            Document.created_at >= ist_midnight_utc,
            Document.created_at < ist_end_utc,
            Document.extraction_status.in_(["pending", "success"]),
        )
        .scalar()
    )

    if today_count >= MAX_UPLOADS_PER_PET_PER_DAY:
        display_name = pet_name or "your pet"
        raise ValueError(
            f"Daily upload limit reached for {display_name}. "
            f"Maximum {MAX_UPLOADS_PER_PET_PER_DAY} uploads per pet per day."
        )


def build_storage_path(
    user_id: UUID,
    pet_id: UUID,
    filename: str,
) -> str:
    """
    Build the Supabase storage path for a file.

    Path format: {user_id}/{pet_id}/{timestamp}_{filename}
    A Unix timestamp prefix is added to prevent duplicate path conflicts
    when the same file is uploaded multiple times.

    Args:
        user_id: UUID of the owning user.
        pet_id: UUID of the pet.
        filename: Original filename of the uploaded file.

    Returns:
        Formatted storage path string.
    """
    import time
    # Prefix filename with timestamp to prevent Supabase duplicate path errors.
    timestamped_filename = f"{int(time.time())}_{filename}"
    return STORAGE_PATH_TEMPLATE.format(
        user_id=str(user_id),
        pet_id=str(pet_id),
        filename=timestamped_filename,
    )


async def upload_to_supabase(
    file_content: bytes,
    storage_path: str,
    mime_type: str,
) -> str:
    """
    Upload a file to the private Supabase storage bucket.

    Bucket name is read from settings.SUPABASE_BUCKET_NAME (env var)
    — never hardcoded. Files are stored privately with no public URLs.

    The sync Supabase SDK call is run in a thread pool via asyncio
    to avoid blocking the event loop during concurrent uploads.

    Args:
        file_content: Raw file bytes.
        storage_path: Path within the bucket ({user_id}/{pet_id}/{filename}).
        mime_type: MIME type of the file for content-type header.

    Returns:
        The storage path where the file was uploaded.

    Raises:
        RuntimeError: If the upload to Supabase fails.
    """
    import asyncio

    # Supabase bucket name from environment — not hardcoded.
    bucket_name = settings.SUPABASE_BUCKET_NAME

    def _sync_upload():
        """Run the sync Supabase SDK upload in a thread."""
        supabase_client = _get_supabase_client()
        supabase_client.storage.from_(bucket_name).upload(
            path=storage_path,
            file=file_content,
            file_options={"content-type": mime_type},
        )

    try:
        # Run sync upload in thread pool to avoid blocking the event loop.
        # This is critical when 100+ users upload simultaneously — without
        # this, each sync upload blocks all other coroutines.
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _sync_upload)

        logger.info(
            "File uploaded to Supabase: bucket=%s, path=%s, mime=%s, size=%d",
            bucket_name,
            storage_path,
            mime_type,
            len(file_content),
        )

        return storage_path

    except Exception as e:
        logger.error(
            "Supabase upload failed: bucket=%s, path=%s, error=%s",
            bucket_name,
            storage_path,
            str(e),
        )
        raise RuntimeError(
            f"Failed to upload file to Supabase: {str(e)}"
        ) from e


def create_document_record(
    db: Session,
    pet_id: UUID,
    file_path: str,
    mime_type: str,
    original_filename: str | None = None,
    source_wamid: str | None = None,
) -> Document:
    """
    Insert a document record into the database.

    The document is created with extraction_status='pending',
    indicating it is ready for GPT extraction processing.
    The original filename is stored as document_name so the dashboard
    can display it even if extraction fails later.

    Args:
        db: SQLAlchemy database session.
        pet_id: UUID of the pet this document belongs to.
        file_path: Supabase storage path of the uploaded file.
        mime_type: MIME type of the uploaded file.
        original_filename: Original filename from the upload (optional).
        source_wamid: WhatsApp message ID that triggered this upload (optional).

    Returns:
        The created Document model instance.
    """
    document = Document(
        pet_id=pet_id,
        file_path=file_path,
        mime_type=mime_type,
        extraction_status="pending",
        document_name=original_filename[:200] if original_filename else None,
        source_wamid=source_wamid,
    )

    db.add(document)
    db.commit()
    db.refresh(document)

    logger.info(
        "Document record created: id=%s, pet_id=%s, path=%s, "
        "mime=%s, extraction_status=pending",
        str(document.id),
        str(pet_id),
        file_path,
        mime_type,
    )

    return document


async def download_from_supabase(storage_path: str) -> bytes | None:
    """
    Download a file from the private Supabase storage bucket.

    Used by the extraction pipeline to retrieve uploaded files
    for GPT processing (vision API for images, text extraction for PDFs).

    The sync Supabase SDK call is run in a thread pool via asyncio
    to avoid blocking the event loop.

    Args:
        storage_path: Path within the bucket ({user_id}/{pet_id}/{filename}).

    Returns:
        Raw file bytes on success, None on failure.
    """
    import asyncio

    bucket_name = settings.SUPABASE_BUCKET_NAME

    def _sync_download() -> bytes:
        """Run the sync Supabase SDK download in a thread."""
        supabase_client = _get_supabase_client()
        return supabase_client.storage.from_(bucket_name).download(storage_path)

    try:
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(None, _sync_download)

        logger.info(
            "File downloaded from Supabase: path=%s, size=%d",
            storage_path, len(data),
        )
        return data

    except Exception as e:
        logger.error(
            "Supabase download failed: path=%s, error=%s",
            storage_path, str(e),
        )
        return None


async def process_document_upload(
    db: Session,
    pet_id: UUID,
    user_id: UUID,
    filename: str,
    file_content: bytes,
    mime_type: str,
    pet_name: str | None = None,
    source_wamid: str | None = None,
) -> Document:
    """
    Full document upload pipeline: validate → store → create record.

    This is the main entry point for document uploads. It performs
    all validation, uploads to Supabase, and creates the database record.
    After this function returns, the document is ready for GPT extraction.

    Steps:
        1. Validate file size (max 10MB from constants).
        2. Validate MIME type (jpeg/png/pdf from constants).
        3. Check daily upload limit (10/pet/day from constants).
        4. Build storage path ({user_id}/{pet_id}/{filename}).
        5. Upload to private Supabase bucket (bucket from env).
        6. Insert document record (extraction_status='pending').

    Args:
        db: SQLAlchemy database session.
        pet_id: UUID of the pet this document belongs to.
        user_id: UUID of the owning user.
        filename: Original filename of the uploaded file.
        file_content: Raw file bytes.
        mime_type: MIME type of the uploaded file.

    Returns:
        The created Document model instance with extraction_status='pending'.

    Raises:
        ValueError: If file fails validation (size, MIME, daily limit).
        RuntimeError: If Supabase upload fails.
    """
    # --- Step 1 & 2: Validate file size and MIME type ---
    validate_file_upload(len(file_content), mime_type)

    # --- Step 3: Check daily upload limit ---
    check_daily_upload_limit(db, pet_id, pet_name=pet_name)

    # --- Step 4: Build storage path ---
    storage_path = build_storage_path(user_id, pet_id, filename)

    # --- Step 5: Upload to Supabase private bucket ---
    await upload_to_supabase(file_content, storage_path, mime_type)

    # --- Step 6: Create document record ---
    document = create_document_record(
        db, pet_id, storage_path, mime_type,
        original_filename=filename, source_wamid=source_wamid,
    )

    return document
