import json
from datetime import datetime, timedelta

from app.services import gpt_extraction


def test_validate_extraction_preserves_diagnostic_values() -> None:
    raw_json = json.dumps(
        {
            "document_name": "Urine Test Report",
            "document_type": "pet_medical",
            "document_category": "Diagnostic",
            "diagnostic_summary": "Mild protein detected.",
            "diagnostic_values": [
                {
                    "test_type": "urine",
                    "parameter_name": "Urine pH",
                    "value_numeric": 7.5,
                    "value_text": None,
                    "unit": None,
                    "reference_range": "6.0-7.0",
                    "status_flag": "high",
                    "observed_at": "2025-02-12",
                }
            ],
            "items": [],
        }
    )

    items, document_name, extracted_pet_name, metadata = gpt_extraction._validate_extraction_json(raw_json)

    assert items == []
    assert document_name == "Urine Test Report"
    assert extracted_pet_name is None
    assert metadata["document_category"] == "Diagnostic"
    assert metadata["diagnostic_values"][0]["parameter_name"] == "Urine pH"


def test_normalize_document_category_accepts_plural_and_case_variants() -> None:
    assert gpt_extraction._normalize_document_category("prescriptions") == "Prescription"
    assert gpt_extraction._normalize_document_category("VACCINATIONS") == "Vaccination"
    assert gpt_extraction._normalize_document_category("lab") == "Diagnostic"


def test_infer_document_category_uses_filename_when_gpt_misses_prescription() -> None:
    category = gpt_extraction._infer_document_category(
        document_name="Health Checkup Report",
        file_path="uploads/Prescription_Chavan_12_02_25.jpg",
        items=[
            {"item_name": "Annual Checkup", "last_done_date": "2025-02-12"},
            {"item_name": "Preventive Blood Test", "last_done_date": "2025-02-12"},
        ],
        vaccination_details=[],
        diagnostic_values=[],
    )

    assert category == "Prescription"


def test_resolve_document_category_overrides_other_with_inferred_diagnostic() -> None:
    resolved = gpt_extraction._resolve_document_category("Other", "Diagnostic")

    assert resolved == "Diagnostic"


def test_extract_date_from_filename_supports_sample_report_names() -> None:
    extracted = gpt_extraction._extract_date_from_filename("uploads/CBC_12_02_25.pdf")

    assert extracted == "2025-02-12"


def test_derive_blood_test_fallback_items_uses_filename_for_cbc_reports() -> None:
    items = gpt_extraction._derive_blood_test_fallback_items(
        extracted_items=[],
        document_name="Blood Test Report",
        file_path="uploads/CBC_12_02_25.pdf",
        document_category="Diagnostic",
        diagnostic_values=[],
    )

    assert items == [{"item_name": "Preventive Blood Test", "last_done_date": "2025-02-12"}]


def test_derive_blood_test_fallback_items_prefers_observed_blood_date() -> None:
    items = gpt_extraction._derive_blood_test_fallback_items(
        extracted_items=[],
        document_name="Blood Test Report",
        file_path="uploads/Blood_29_01_25.pdf",
        document_category="Diagnostic",
        diagnostic_values=[
            {
                "test_type": "blood",
                "parameter_name": "Creatinine",
                "observed_at": "2025-01-28",
            }
        ],
    )

    assert items == [{"item_name": "Preventive Blood Test", "last_done_date": "2025-01-28"}]


def test_validate_extraction_salvages_metadata_from_malformed_json() -> None:
    raw_json = (
        '{'
        '"document_name": "Blood Test Report", '
        '"document_type": "pet_medical", '
        '"document_category": "Diagnostic", '
        '"pet_name": "ZAYN", '
        '"doctor_name": "Dr. D. P. Chaudhari", '
        '"clinic_name": "UNIQUE LAB NEW", '
        '"diagnostic_values": ['
    )

    items, document_name, extracted_pet_name, metadata = gpt_extraction._validate_extraction_json(raw_json)

    assert items == []
    assert document_name == "Blood Test Report"
    assert extracted_pet_name == "ZAYN"
    assert metadata["document_category"] == "Diagnostic"
    assert metadata["doctor_name"] == "Dr. D. P. Chaudhari"
    assert metadata["clinic_name"] == "UNIQUE LAB NEW"


def test_validate_extraction_skips_future_last_done_dates() -> None:
    future_date = (datetime.utcnow().date() + timedelta(days=30)).isoformat()
    raw_json = json.dumps(
        {
            "document_name": "Vaccination Certificate",
            "document_type": "pet_medical",
            "document_category": "Vaccination",
            "items": [
                {"item_name": "Rabies Vaccine", "last_done_date": future_date},
                {"item_name": "Core Vaccine", "last_done_date": "2025-05-06"},
            ],
        }
    )

    items, _, _, _ = gpt_extraction._validate_extraction_json(raw_json)

    assert items == [{"item_name": "Core Vaccine", "last_done_date": "2025-05-06"}]