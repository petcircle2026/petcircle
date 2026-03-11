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
import os
import re
from datetime import datetime
from uuid import UUID
from sqlalchemy.orm import Session
from app.models.document import Document
from app.models.pet import Pet
from app.models.preventive_master import PreventiveMaster
from app.models.diagnostic_test_result import DiagnosticTestResult
from app.core.constants import (
    OPENAI_EXTRACTION_MODEL,
    OPENAI_EXTRACTION_TEMPERATURE,
    OPENAI_EXTRACTION_MAX_TOKENS,
    DOCUMENT_CATEGORIES,
)
from app.config import settings
from app.utils.retry import retry_openai_call
from app.utils.date_utils import parse_date, format_date_for_db


logger = logging.getLogger(__name__)


def _normalize_document_category(raw_category: str | None) -> str | None:
    """Normalize GPT category output to one of the dashboard's canonical values."""
    value = (raw_category or "").strip().lower()
    if not value:
        return None

    aliases = {
        "vaccination": "Vaccination",
        "vaccinations": "Vaccination",
        "vaccine": "Vaccination",
        "vaccines": "Vaccination",
        "prescription": "Prescription",
        "prescriptions": "Prescription",
        "rx": "Prescription",
        "medication": "Prescription",
        "diagnostic": "Diagnostic",
        "diagnostics": "Diagnostic",
        "lab": "Diagnostic",
        "laboratory": "Diagnostic",
        "other": "Other",
        "misc": "Other",
        "miscellaneous": "Other",
    }
    if value in aliases:
        return aliases[value]

    for category in DOCUMENT_CATEGORIES:
        if value == category.lower():
            return category

    return None


def _infer_document_category(
    document_name: str | None,
    file_path: str | None,
    items: list[dict],
    vaccination_details: list[dict],
    diagnostic_values: list[dict],
) -> str:
    """Infer a document category when GPT omits or misformats it."""
    name_text = (document_name or "").strip().lower()
    file_text = os.path.basename(file_path or "").strip().lower()
    combined_text = f"{name_text} {file_text}"

    if any(keyword in combined_text for keyword in ("prescription", "rx", "medicine", "medication")):
        return "Prescription"
    if any(keyword in combined_text for keyword in ("vaccin", "rabies", "dhpp", "fvrcp", "booster")):
        return "Vaccination"
    if any(keyword in combined_text for keyword in (
        "blood",
        "urine",
        "diagnostic",
        "lab",
        "laboratory",
        "cbc",
        "biochemistry",
        "hematology",
        "haematology",
        "urinalysis",
        "x-ray",
        "xray",
    )):
        return "Diagnostic"

    if vaccination_details:
        return "Vaccination"
    if diagnostic_values:
        return "Diagnostic"

    item_names = {
        _normalize_preventive_item_name(str(item.get("item_name") or ""))
        for item in items
        if item.get("item_name")
    }
    if item_names & {"rabies vaccine", "core vaccine", "feline core"}:
        return "Vaccination"
    if "preventive blood test" in item_names:
        return "Diagnostic"
    if any(item_name in item_names for item_name in ("annual checkup", "dental check", "deworming", "tick/flea")):
        return "Prescription"

    return "Other"


def _append_single_extracted_date_to_filename(
    original_filename: str,
    extracted_items: list[dict],
) -> str:
    """
    Preserve original filename and append a date only when extraction has one unique date.

    Rules:
      - If exactly one valid unique `last_done_date` exists, append it to the filename.
      - If zero or multiple unique dates exist, return the original filename unchanged.
      - If the filename already contains that date, return unchanged (idempotent).
    """
    unique_dates: set[str] = set()
    for item in extracted_items:
        date_str = item.get("last_done_date")
        if not date_str:
            continue

        # Keep only valid canonical dates.
        try:
            normalized = datetime.strptime(str(date_str), "%Y-%m-%d").strftime("%Y-%m-%d")
        except ValueError:
            continue

        unique_dates.add(normalized)

    if len(unique_dates) != 1:
        return original_filename

    only_date = next(iter(unique_dates))
    if only_date in original_filename:
        return original_filename

    # Append date before extension when present.
    dot = original_filename.rfind(".")
    if dot > 0:
        return f"{original_filename[:dot]}_{only_date}{original_filename[dot:]}"
    return f"{original_filename}_{only_date}"


# --- Expected JSON keys from GPT extraction ---
# Each extracted item must have these keys.
# Any missing key causes validation failure.
REQUIRED_EXTRACTION_KEYS = {"item_name", "last_done_date"}

# --- System prompt for GPT extraction ---
# Instructs GPT to extract structured preventive health data only.
# No medical advice. No inference beyond the document content.
EXTRACTION_SYSTEM_PROMPT = (
    "You are a veterinary document data extractor. "
    "Analyze the provided document and return a JSON object with these keys:\n"
    '  - "document_name": string (a short descriptive name for this document, '
    "e.g., 'Blood Test Report', 'Vaccination Certificate', 'Deworming Record', "
    "'Vet Prescription', 'Health Checkup Report')\n"
    '  - "document_type": "pet_medical" or "not_pet_related" '
    "(set to 'not_pet_related' if the document is clearly NOT a pet/veterinary document, "
    "e.g., a human medical report, invoice, random photo, etc.)\n"
    '  - "document_category": one of "Vaccination", "Prescription", "Diagnostic", "Other" '
    "(classify the document: Vaccination for vaccine certificates/records, "
    "Prescription for vet prescriptions/medication records, "
    "Diagnostic for blood tests/urine tests/lab reports/x-rays, "
    "Other for anything else)\n"
    '  - "diagnostic_summary": string or null (for Diagnostic documents only — '
    "provide a 1-2 sentence plain-language summary of key findings; null otherwise)\n"
    '  - "diagnostic_values": array (for Diagnostic blood/urine reports), each with:\n'
    '    - "test_type": "blood" or "urine"\n'
    '    - "parameter_name": string (e.g., Hemoglobin, WBC, Creatinine, Urine pH)\n'
    '    - "value_numeric": number or null\n'
    '    - "value_text": string or null (use when numeric is not available)\n'
    '    - "unit": string or null\n'
    '    - "reference_range": string or null\n'
    '    - "status_flag": "low" | "normal" | "high" | "abnormal" | null\n'
    '    - "observed_at": date string (same accepted formats) or null\n'
    '  - "pet_name": string or null (the name of the pet mentioned in the document, '
    "if explicitly stated; null if no pet name is found)\n"
    '  - "doctor_name": string or null (veterinarian/doctor name if explicitly mentioned)\n'
    '  - "clinic_name": string or null (hospital/clinic name if explicitly mentioned)\n'
    '  - "vaccination_details": array of objects (for vaccine records; [] if none). '
    "Each object may include: vaccine_name, vaccine_name_raw, dose, dose_unit, "
    "route, manufacturer, batch_number, next_due_date, administered_by, notes\n"
    '  - "items": array of objects, each with:\n'
    '    - "item_name": string (MUST be one of the tracked items listed below)\n'
    '    - "last_done_date": string (the date the item was done, '
    "in DD/MM/YYYY or DD-MM-YYYY or DD-Mon-YYYY or DD Month YYYY or YYYY-MM-DD format)\n"
    '    - "dose": string or null (dose amount, if present in the document)\n'
    '    - "doctor_name": string or null (doctor name for that line item, if present)\n'
    '    - "clinic_name": string or null (clinic name for that line item, if present)\n'
    '    - "batch_number": string or null (vaccine lot/batch number, if present)\n\n'
    "Tracked preventive items (use these EXACT names):\n"
    "  - Rabies Vaccine\n"
    "  - Core Vaccine\n"
    "  - Feline Core\n"
    "  - Deworming\n"
    "  - Tick/Flea\n"
    "  - Annual Checkup\n"
    "  - Preventive Blood Test\n"
    "  - Dental Check\n\n"
    "Rules:\n"
    "- Extract ONLY items that match the tracked preventive items above.\n"
    "- A blood test report counts as 'Preventive Blood Test' — use the report date.\n"
    "- Do NOT provide medical advice or interpretation.\n"
    "- Do NOT infer dates — only extract what is explicitly stated.\n"
    "- Extract the pet's name EXACTLY as written in the document (if present).\n"
    "- For vaccination records, extract all available vaccine details (dose, batch, doctor, clinic, next due date) without guessing.\n"
    "- If any field is missing in the document, use null for that field.\n"
    "- If the document is not pet/veterinary related, set document_type to 'not_pet_related' and items to [].\n"
    '- If no preventive items are found, return {"document_name": "...", "document_type": "pet_medical", '
    '"document_category": "...", "diagnostic_summary": null, "pet_name": null, "items": []}\n'
    "- Return valid JSON only — no markdown, no explanation, no extra text."
)


_openai_extraction_client = None


def _get_openai_extraction_client():
    """Return a cached AsyncOpenAI client for extraction (created on first call)."""
    global _openai_extraction_client
    if _openai_extraction_client is None:
        from openai import AsyncOpenAI
        _openai_extraction_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _openai_extraction_client


async def _call_openai_extraction(document_text: str) -> str:
    """
    Call OpenAI GPT to extract structured data from document text.

    Used for PDF text content. For images, use _call_openai_extraction_vision().

    Args:
        document_text: The text content of the uploaded document.

    Returns:
        Raw JSON string response from GPT.

    Raises:
        Exception: If all retry attempts fail (propagated from retry_openai_call).
    """
    client = _get_openai_extraction_client()

    async def _make_call() -> str:
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

    return await retry_openai_call(_make_call)


async def _call_openai_extraction_vision(image_data_uri: str) -> str:
    """
    Call OpenAI GPT vision API to extract data from an image.

    Sends the image as a base64 data URI to GPT-4.1's vision capability.
    Used for JPEG/PNG uploads where text extraction is not possible.

    Args:
        image_data_uri: Base64 data URI (data:image/jpeg;base64,...).

    Returns:
        Raw JSON string response from GPT.

    Raises:
        Exception: If all retry attempts fail.
    """
    client = _get_openai_extraction_client()

    async def _make_call() -> str:
        response = await client.chat.completions.create(
            model=OPENAI_EXTRACTION_MODEL,
            temperature=OPENAI_EXTRACTION_TEMPERATURE,
            max_tokens=OPENAI_EXTRACTION_MAX_TOKENS,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Extract preventive health data from this veterinary document image.",
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": image_data_uri, "detail": "high"},
                        },
                    ],
                },
            ],
        )
        return response.choices[0].message.content

    return await retry_openai_call(_make_call)


def _validate_extraction_json(raw_json: str) -> tuple[list[dict], str | None, str | None, dict]:
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
        Tuple of (validated items list, document_name or None, extracted_pet_name or None, metadata dict).
        metadata contains: document_type, document_category, diagnostic_summary,
        doctor_name, clinic_name, vaccination_details.

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

    # Extract document_name, pet_name, and new classification fields.
    document_name = None
    extracted_pet_name = None
    metadata = {
        "document_type": "pet_medical",
        "document_category": None,
        "diagnostic_summary": None,
        "diagnostic_values": [],
        "doctor_name": None,
        "clinic_name": None,
        "vaccination_details": [],
    }
    if isinstance(parsed, dict):
        document_name = parsed.get("document_name")
        extracted_pet_name = parsed.get("pet_name")
        # Extract classification metadata.
        metadata["document_type"] = parsed.get("document_type", "pet_medical")
        metadata["document_category"] = _normalize_document_category(parsed.get("document_category"))
        metadata["diagnostic_summary"] = parsed.get("diagnostic_summary")
        raw_diagnostic_values = parsed.get("diagnostic_values")
        if isinstance(raw_diagnostic_values, list):
            metadata["diagnostic_values"] = raw_diagnostic_values
        metadata["doctor_name"] = parsed.get("doctor_name")
        metadata["clinic_name"] = parsed.get("clinic_name")
        raw_vaccination_details = parsed.get("vaccination_details")
        if isinstance(raw_vaccination_details, list):
            metadata["vaccination_details"] = raw_vaccination_details

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

    return validated, document_name, extracted_pet_name, metadata


def _load_species_masters(db: Session, species: str) -> list[PreventiveMaster]:
    """
    Load all preventive master records for a species (including 'both').

    Loads once per extraction call and caches in-memory to avoid
    repeated DB queries when matching multiple extracted items.

    Args:
        db: SQLAlchemy database session.
        species: Pet species ('dog' or 'cat').

    Returns:
        List of PreventiveMaster records for this species.
    """
    return (
        db.query(PreventiveMaster)
        .filter(PreventiveMaster.species.in_([species, "both"]))
        .all()
    )


def _normalize_preventive_item_name(name: str) -> str:
    """Normalize extracted preventive item names for robust matching."""
    value = (name or "").strip().lower()
    value = re.sub(r"\s*\([^)]*\)", "", value)  # drop parenthetical clarifiers
    value = re.sub(r"\s+", " ", value)
    return value


def _match_preventive_master_from_list(
    masters: list[PreventiveMaster],
    item_name: str,
) -> PreventiveMaster | None:
    """Match an extracted item name to a preventive_master record."""
    item_normalized = _normalize_preventive_item_name(item_name)

    aliases = {
        "core vaccine dhpp": "core vaccine",
        "core vaccine dhppi": "core vaccine",
        "dhpp": "core vaccine",
        "dhppi": "core vaccine",
        "feline core fvrcp": "feline core",
        "fvrcp": "feline core",
    }
    item_normalized = aliases.get(item_normalized, item_normalized)

    # Try normalized exact match first.
    for master in masters:
        if _normalize_preventive_item_name(master.item_name) == item_normalized:
            return master

    # Try partial match in both directions — GPT may abbreviate or rephrase.
    for master in masters:
        master_normalized = _normalize_preventive_item_name(master.item_name)
        if (
            item_normalized in master_normalized
            or master_normalized in item_normalized
        ):
            return master

    return None


async def extract_and_process_document(
    db: Session,
    document_id: UUID,
    document_text: str,
    file_bytes: bytes | None = None,
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
        # Route to vision API for images, text API for PDFs.
        logger.info(
            "Starting GPT extraction: document_id=%s, pet_id=%s, mime=%s",
            str(document_id),
            str(pet.id),
            document.mime_type,
        )

        if file_bytes and document.mime_type in ("image/jpeg", "image/png"):
            # Images: use GPT vision API with base64-encoded image.
            from app.utils.file_reader import encode_image_base64
            data_uri = encode_image_base64(file_bytes, document.mime_type)
            raw_json = await _call_openai_extraction_vision(data_uri)
        elif file_bytes and document.mime_type == "application/pdf":
            # PDFs: extract text first, then send to GPT.
            from app.utils.file_reader import extract_pdf_text
            pdf_text = extract_pdf_text(file_bytes)
            if pdf_text and len(pdf_text.strip()) > 20:
                raw_json = await _call_openai_extraction(
                    f"Veterinary document text:\n\n{pdf_text}"
                )
            else:
                # Scanned PDF with no extractable text — mark and skip.
                logger.warning(
                    "PDF has no extractable text (scanned): document_id=%s",
                    str(document_id),
                )
                document.extraction_status = "failed"
                db.commit()
                results["status"] = "failed"
                results["errors"].append(
                    "This PDF appears to be a scanned image. "
                    "Please upload photos of the document instead."
                )
                return results
        else:
            # Fallback: use whatever text was passed (for backwards compatibility).
            raw_json = await _call_openai_extraction(document_text)

        # --- Step 2: Validate and normalize ---
        extracted_items, document_name, extracted_pet_name, metadata = _validate_extraction_json(raw_json)
        results["items_extracted"] = len(extracted_items)
        results["document_type"] = metadata["document_type"]
        results["document_category"] = metadata["document_category"]
        results["diagnostic_summary"] = metadata["diagnostic_summary"]
        results["diagnostic_values"] = metadata.get("diagnostic_values", [])
        results["doctor_name"] = metadata["doctor_name"]
        results["clinic_name"] = metadata["clinic_name"]
        results["vaccination_details"] = metadata["vaccination_details"]

        document_category = metadata["document_category"] or _infer_document_category(
            document_name=document_name or document.document_name,
            file_path=document.file_path,
            items=extracted_items,
            vaccination_details=metadata.get("vaccination_details", []),
            diagnostic_values=metadata.get("diagnostic_values", []),
        )
        results["document_category"] = document_category

        # Keep original filename; append a date only when exactly one date is present.
        if document.document_name:
            document.document_name = _append_single_extracted_date_to_filename(
                str(document.document_name), extracted_items
            )[:200]
        if document_category:
            document.document_category = document_category
        if metadata["doctor_name"]:
            document.doctor_name = str(metadata["doctor_name"])[:200]
        if metadata["clinic_name"]:
            document.hospital_name = str(metadata["clinic_name"])[:200]

        # Enrich top-level doctor/clinic from item-level values when missing.
        if not results["doctor_name"]:
            for item in extracted_items:
                item_doctor = item.get("doctor_name")
                if item_doctor:
                    results["doctor_name"] = item_doctor
                    document.doctor_name = str(item_doctor)[:200]
                    break

        if not results["clinic_name"]:
            for item in extracted_items:
                item_clinic = item.get("clinic_name")
                if item_clinic:
                    results["clinic_name"] = item_clinic
                    document.hospital_name = str(item_clinic)[:200]
                    break

        # Replace previously extracted diagnostic values for this document.
        db.query(DiagnosticTestResult).filter(
            DiagnosticTestResult.document_id == document.id
        ).delete()

        diagnostic_values = metadata.get("diagnostic_values") or []
        for raw in diagnostic_values:
            if not isinstance(raw, dict):
                continue

            test_type = str(raw.get("test_type") or "").strip().lower()
            if test_type not in ("blood", "urine"):
                continue

            parameter_name = str(raw.get("parameter_name") or "").strip()
            if not parameter_name:
                continue

            value_numeric = raw.get("value_numeric")
            if value_numeric is not None:
                try:
                    value_numeric = float(value_numeric)
                except (TypeError, ValueError):
                    value_numeric = None

            value_text = raw.get("value_text")
            if value_numeric is None and (value_text is None or str(value_text).strip() == ""):
                continue

            observed_at = None
            if raw.get("observed_at"):
                try:
                    observed_at = parse_date(str(raw.get("observed_at")))
                except ValueError:
                    observed_at = None

            status_flag = raw.get("status_flag")
            if status_flag is not None:
                status_flag = str(status_flag).strip().lower()
                if status_flag not in ("low", "normal", "high", "abnormal"):
                    status_flag = None

            db.add(DiagnosticTestResult(
                pet_id=pet.id,
                document_id=document.id,
                test_type=test_type,
                parameter_name=parameter_name[:120],
                value_numeric=value_numeric,
                value_text=(str(value_text).strip()[:200] if value_text is not None else None),
                unit=(str(raw.get("unit")).strip()[:60] if raw.get("unit") is not None else None),
                reference_range=(
                    str(raw.get("reference_range")).strip()[:120]
                    if raw.get("reference_range") is not None
                    else None
                ),
                status_flag=status_flag,
                observed_at=observed_at,
            ))

        # --- Non-pet document check ---
        # If GPT determined this is not a pet/veterinary document,
        # mark as success (it was processed) but return early with message.
        if metadata["document_type"] == "not_pet_related":
            logger.info(
                "Document classified as not pet-related: document_id=%s",
                str(document_id),
            )
            document.extraction_status = "success"
            db.commit()
            results["errors"].append(
                "This doesn't appear to be a pet/veterinary document. "
                "Please upload veterinary records, vaccination certificates, "
                "or prescription documents."
            )
            return results

        # --- Pet name mismatch check ---
        # If GPT extracted a pet name from the document, verify it matches
        # the registered pet name. If not, flag the document and skip extraction.
        if extracted_pet_name and pet.name:
            if extracted_pet_name.strip().lower() != pet.name.strip().lower():
                logger.warning(
                    "Pet name mismatch: document says '%s', registered pet is '%s'. "
                    "Flagging document %s — skipping extraction.",
                    extracted_pet_name,
                    pet.name,
                    str(document_id),
                )
                document.extraction_status = "failed"
                db.commit()
                results["status"] = "failed"
                results["errors"].append(
                    f"Pet name mismatch: document mentions '{extracted_pet_name}' "
                    f"but this upload is for '{pet.name}'. "
                    f"Please upload documents that belong to {pet.name}."
                )
                return results

        if not extracted_items:
            logger.info(
                "No preventive items extracted from document: %s",
                str(document_id),
            )
            document.extraction_status = "success"
            db.commit()
            return results

        # --- Step 3 & 4: Process each extracted item ---
        # Pre-load all preventive masters for this species once
        # to avoid per-item DB queries (N+1 prevention).
        species_masters = _load_species_masters(db, pet.species)

        for item in extracted_items:
            try:
                item_name = item["item_name"]
                last_done_date_str = item["last_done_date"]
                last_done_date = parse_date(last_done_date_str)

                # Match to a preventive_master record using in-memory list.
                # Recurrence days and all config are read from DB — never hardcoded.
                master = _match_preventive_master_from_list(species_masters, item_name)

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
        results["status"] = "failed"
        results["errors"].append(f"Extraction failed: {str(e)}")

        logger.error(
            "GPT extraction failed: document_id=%s, error=%s",
            str(document_id),
            str(e),
        )

        # Persist 'failed' status. If commit fails (broken session),
        # rollback and retry with a fresh transaction. Without this,
        # the document stays 'pending' and gets ghost-re-extracted
        # in the next batch for this pet.
        try:
            document.extraction_status = "failed"
            db.commit()
        except Exception:
            try:
                db.rollback()
                document.extraction_status = "failed"
                db.commit()
            except Exception as commit_err:
                logger.error(
                    "CRITICAL: Could not persist failed status for doc %s: %s",
                    str(document_id), str(commit_err),
                )
                try:
                    db.rollback()
                except Exception:
                    pass

    return results
