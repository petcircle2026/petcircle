import json

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