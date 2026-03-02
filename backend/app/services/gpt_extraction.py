"""
PetCircle Phase 1 — GPT Extraction Service (Module 7)

Extracts structured preventive health data from uploaded pet documents
using OpenAI GPT. This service processes documents after upload and
routes extracted data to the preventive engine (conflict detection
or record creation).

Extraction pipeline:
    Document (pending) → GPT extraction → Validate JSON → Normalize dates
        → Pass to conflict engine or create preventive record
        → Update extraction_status

Model configuration (all from constants — never hardcoded):
    - Model: OPENAI_EXTRACTION_MODEL (gpt-4.1)
    - Temperature: OPENAI_EXTRACTION_TEMPERATURE (0)
    - Max tokens: OPENAI_EXTRACTION_MAX_TOKENS (1500)
    - Response format: JSON only

Retry policy:
    - Uses retry_openai_call() from utils/retry.py.
    - 3 attempts total (1s, 2s backoff) — configured in constants.
    - On final failure: extraction_status='failed', log error, continue.

Rules:
    - No medical advice in extraction.
    - All dates normalized to YYYY-MM-DD.
    - JSON keys strictly validated.
    - Extraction failures never crash the application.
    - OpenAI API key from environment (settings.OPENAI_API_KEY) — never hardcoded.
"""

import json
import logging
from uuid import UUID
from sqlalchemy.orm import Session
from app.models.document import Document
from app.models.pet import Pet
from app.models.preventive_master import PreventiveMaster
from app.core.constants import (
    OPENAI_EXTRACTION_MODEL,
    OPENAI_EXTRACTION_TEMPERATURE,
    OPENAI_EXTRACTION_MAX_TOKENS,
)
from app.config import settings
from app.utils.retry import retry_openai_call
from app.utils.date_utils import parse_date, format_date_for_db


logger = logging.getLogger(__name__)


# --- Expected JSON keys from GPT extraction ---
# Each extracted item must have these keys.
# Any missing key causes validation failure.
REQUIRED_EXTRACTION_KEYS = {"item_name", "last_done_date"}

# --- System prompt for GPT extraction ---
# Instructs GPT to extract structured preventive health data only.
# No medical advice. No inference beyond the document content.
EXTRACTION_SYSTEM_PROMPT = (
    "You are a veterinary document data extractor. "
    "Extract preventive health items from the provided pet document. "
    "Return ONLY a JSON array of objects, each with these exact keys:\n"
    '  - "item_name": string (the preventive health item name, '
    "e.g., 'Rabies Vaccine', 'Deworming')\n"
    '  - "last_done_date": string (the date the item was done, '
    "in DD/MM/YYYY or DD-MM-YYYY or DD Month YYYY or YYYY-MM-DD format)\n\n"
    "Rules:\n"
    "- Extract ONLY preventive health items (vaccines, deworming, checkups, etc.).\n"
    "- Do NOT provide medical advice or interpretation.\n"
    "- Do NOT infer dates — only extract what is explicitly stated.\n"
    "- If no preventive items are found, return an empty array: []\n"
    "- Return valid JSON only — no markdown, no explanation, no extra text."
)


async def _call_openai_extraction(document_text: str) -> str:
    """
    Call OpenAI GPT to extract structured data from document text.

    Model configuration is loaded from constants — never hardcoded:
        - Model: OPENAI_EXTRACTION_MODEL (gpt-4.1)
        - Temperature: OPENAI_EXTRACTION_TEMPERATURE (0)
        - Max tokens: OPENAI_EXTRACTION_MAX_TOKENS (1500)

    The API key is loaded from settings.OPENAI_API_KEY (env var).

    Args:
        document_text: The text content of the uploaded document.

    Returns:
        Raw JSON string response from GPT.

    Raises:
        Exception: If all retry attempts fail (propagated from retry_openai_call).
    """
    from openai import AsyncOpenAI

    # API key from environment — never hardcoded.
    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    async def _make_call() -> str:
        """Inner function wrapped by retry_openai_call."""
        response = await client.chat.completions.create(
            model=OPENAI_EXTRACTION_MODEL,
            temperature=OPENAI_EXTRACTION_TEMPERATURE,
            max_tokens=OPENAI_EXTRACTION_MAX_TOKENS,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": document_text},
            ],
        )
        return response.choices[0].message.content

    # Retry with backoff: 3 attempts (1s, 2s) — from constants via retry utility.
    return await retry_openai_call(_make_call)


def _validate_extraction_json(raw_json: str) -> list[dict]:
    """
    Parse and validate the JSON response from GPT extraction.

    Validation rules:
        - Must be valid JSON.
        - Must contain a list of objects (or a wrapper with 'items' key).
        - Each object must contain all REQUIRED_EXTRACTION_KEYS.
        - Dates must be parseable by parse_date() from date_utils.

    Args:
        raw_json: Raw JSON string from GPT response.

    Returns:
        List of validated extraction dictionaries with normalized dates.

    Raises:
        ValueError: If JSON is invalid or missing required keys.
    """
    # Parse JSON — reject non-JSON responses.
    try:
        parsed = json.loads(raw_json)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"GPT returned invalid JSON: {str(e)}"
        ) from e

    # Handle both direct array and wrapper object formats.
    # GPT with json_object mode returns an object, not an array.
    # Accept {"items": [...]} or direct [...] format.
    if isinstance(parsed, dict):
        # Look for common wrapper keys.
        if "items" in parsed:
            items = parsed["items"]
        elif "data" in parsed:
            items = parsed["data"]
        elif "results" in parsed:
            items = parsed["results"]
        else:
            # Single item wrapped in object — treat as single-item list.
            items = [parsed]
    elif isinstance(parsed, list):
        items = parsed
    else:
        raise ValueError(
            f"GPT returned unexpected type: {type(parsed).__name__}. "
            f"Expected JSON array or object."
        )

    if not isinstance(items, list):
        raise ValueError(
            f"Extracted items must be a list, got {type(items).__name__}."
        )

    # Validate each extracted item.
    validated = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            logger.warning(
                "Skipping non-dict extraction item at index %d: %s",
                i, str(item),
            )
            continue

        # Check required keys.
        missing_keys = REQUIRED_EXTRACTION_KEYS - set(item.keys())
        if missing_keys:
            logger.warning(
                "Skipping extraction item at index %d — missing keys: %s. "
                "Item: %s",
                i, missing_keys, str(item),
            )
            continue

        # Normalize and validate the date.
        try:
            parsed_date = parse_date(str(item["last_done_date"]))
            item["last_done_date"] = format_date_for_db(parsed_date)
        except ValueError as e:
            logger.warning(
                "Skipping extraction item at index %d — invalid date: %s. "
                "Item: %s",
                i, str(e), str(item),
            )
            continue

        validated.append(item)

    return validated


def _match_preventive_master(
    db: Session,
    item_name: str,
    species: str,
) -> PreventiveMaster | None:
    """
    Match an extracted item name to a preventive_master record.

    Uses case-insensitive matching against the frozen preventive_master
    table. The preventive_master table is the source of truth for all
    preventive items — recurrence_days and other values are always
    read from this table, never hardcoded.

    Args:
        db: SQLAlchemy database session.
        item_name: Extracted item name from GPT (e.g., 'Rabies Vaccine').
        species: Pet species ('dog' or 'cat').

    Returns:
        Matching PreventiveMaster record, or None if no match found.
    """
    # Try exact match first (case-insensitive).
    master = (
        db.query(PreventiveMaster)
        .filter(
            PreventiveMaster.item_name.ilike(item_name),
            PreventiveMaster.species.in_([species, "both"]),
        )
        .first()
    )

    if master:
        return master

    # Try partial match — GPT may abbreviate or rephrase.
    # e.g., "Rabies" → "Rabies Vaccine"
    master = (
        db.query(PreventiveMaster)
        .filter(
            PreventiveMaster.item_name.ilike(f"%{item_name}%"),
            PreventiveMaster.species.in_([species, "both"]),
        )
        .first()
    )

    return master


async def extract_and_process_document(
    db: Session,
    document_id: UUID,
    document_text: str,
) -> dict:
    """
    Run GPT extraction on a document and process the results.

    This is the main extraction pipeline entry point. It:
        1. Calls OpenAI GPT to extract preventive data from the document.
        2. Validates and normalizes the extraction JSON.
        3. For each extracted item, checks for conflicts via the conflict engine.
        4. Creates or updates preventive records as needed.
        5. Updates the document's extraction_status.

    On failure at any step:
        - extraction_status is set to 'failed'.
        - The error is logged.
        - The application does NOT crash.

    Args:
        db: SQLAlchemy database session.
        document_id: UUID of the document to process.
        document_text: Text content of the document (OCR output or raw text).

    Returns:
        Dictionary with extraction results:
            - status: 'success' or 'failed'
            - document_id: the processed document ID
            - items_extracted: count of valid items extracted
            - items_processed: count of items successfully processed
            - errors: list of error messages for failed items
    """
    # Import here to avoid circular imports.
    from app.services.conflict_engine import check_and_create_conflict
    from app.services.preventive_calculator import create_preventive_record

    results = {
        "status": "success",
        "document_id": str(document_id),
        "items_extracted": 0,
        "items_processed": 0,
        "errors": [],
    }

    # Load the document record.
    document = (
        db.query(Document)
        .filter(Document.id == document_id)
        .first()
    )

    if not document:
        return {
            "status": "failed",
            "document_id": str(document_id),
            "items_extracted": 0,
            "items_processed": 0,
            "errors": [f"Document not found: {document_id}"],
        }

    # Load the pet for species matching.
    pet = db.query(Pet).filter(Pet.id == document.pet_id).first()
    if not pet:
        document.extraction_status = "failed"
        db.commit()
        return {
            "status": "failed",
            "document_id": str(document_id),
            "items_extracted": 0,
            "items_processed": 0,
            "errors": [f"Pet not found for document: {document_id}"],
        }

    try:
        # --- Step 1: Call GPT extraction ---
        logger.info(
            "Starting GPT extraction: document_id=%s, pet_id=%s",
            str(document_id),
            str(pet.id),
        )

        raw_json = await _call_openai_extraction(document_text)

        # --- Step 2: Validate and normalize ---
        extracted_items = _validate_extraction_json(raw_json)
        results["items_extracted"] = len(extracted_items)

        if not extracted_items:
            logger.info(
                "No preventive items extracted from document: %s",
                str(document_id),
            )
            document.extraction_status = "success"
            db.commit()
            return results

        # --- Step 3 & 4: Process each extracted item ---
        for item in extracted_items:
            try:
                item_name = item["item_name"]
                last_done_date_str = item["last_done_date"]
                last_done_date = parse_date(last_done_date_str)

                # Match to a preventive_master record.
                # Recurrence days and all config are read from DB — never hardcoded.
                master = _match_preventive_master(db, item_name, pet.species)

                if not master:
                    logger.warning(
                        "No preventive_master match for '%s' (species=%s). "
                        "Skipping. document_id=%s",
                        item_name,
                        pet.species,
                        str(document_id),
                    )
                    results["errors"].append(
                        f"No match for item: {item_name}"
                    )
                    continue

                # Check for conflicts before creating/updating record.
                # If a record already exists with a different date,
                # the conflict engine creates a conflict_flag.
                conflict = check_and_create_conflict(
                    db=db,
                    pet_id=pet.id,
                    preventive_master_id=master.id,
                    new_date=last_done_date,
                )

                if conflict:
                    # Conflict detected — do not create a new record.
                    # The conflict must be resolved by the user first.
                    logger.info(
                        "Conflict created for %s: conflict_id=%s, "
                        "document_id=%s",
                        item_name,
                        str(conflict.id),
                        str(document_id),
                    )
                    results["items_processed"] += 1
                else:
                    # No conflict — create or update preventive record.
                    # compute_next_due_date uses master.recurrence_days from DB.
                    create_preventive_record(
                        db=db,
                        pet_id=pet.id,
                        preventive_master_id=master.id,
                        last_done_date=last_done_date,
                    )

                    logger.info(
                        "Preventive record created for %s: pet_id=%s, "
                        "date=%s, document_id=%s",
                        item_name,
                        str(pet.id),
                        str(last_done_date),
                        str(document_id),
                    )
                    results["items_processed"] += 1

            except Exception as e:
                # Individual item failure — log and continue.
                # Never crash on single-item extraction errors.
                logger.error(
                    "Error processing extracted item '%s': %s. "
                    "document_id=%s",
                    item.get("item_name", "unknown"),
                    str(e),
                    str(document_id),
                )
                results["errors"].append(
                    f"Error processing {item.get('item_name', 'unknown')}: {str(e)}"
                )

        # --- Step 5: Update extraction status ---
        document.extraction_status = "success"
        db.commit()

        logger.info(
            "GPT extraction completed: document_id=%s, "
            "extracted=%d, processed=%d, errors=%d",
            str(document_id),
            results["items_extracted"],
            results["items_processed"],
            len(results["errors"]),
        )

    except Exception as e:
        # Extraction-level failure — mark as failed, do not crash.
        # This catches GPT call failures, JSON parse failures, etc.
        document.extraction_status = "failed"
        db.commit()

        results["status"] = "failed"
        results["errors"].append(f"Extraction failed: {str(e)}")

        logger.error(
            "GPT extraction failed: document_id=%s, error=%s",
            str(document_id),
            str(e),
        )

    return results
