import json

from app.services.gpt_extraction import (
    _pet_name_matches_document_name,
    _select_best_doctor_name,
    _validate_extraction_json,
)


def test_vaccination_category_filters_annual_checkup_items() -> None:
    raw = json.dumps(
        {
            "document_name": "Pet Vaccination & Health Checkup",
            "document_type": "pet_medical",
            "document_category": "Vaccination",
            "items": [
                {"item_name": "Core Vaccine", "last_done_date": "28/03/2023"},
                {"item_name": "Annual Checkup", "last_done_date": "28/03/2023"},
                {"item_name": "Rabies Vaccine", "last_done_date": "23/11/2024"},
            ],
        }
    )

    items, _doc_name, _pet_name, _metadata = _validate_extraction_json(raw)

    assert [item["item_name"] for item in items] == ["Core Vaccine", "Rabies Vaccine"]


def test_vaccination_details_next_due_date_is_normalized() -> None:
    raw = json.dumps(
        {
            "document_name": "Pet Vaccination & Health Checkup",
            "document_type": "pet_medical",
            "document_category": "Vaccination",
            "items": [
                {"item_name": "Rabies Vaccine", "last_done_date": "23/11/2024"},
            ],
            "vaccination_details": [
                {"vaccine_name": "Rabies", "next_due_date": "06/05/2026"},
                {"vaccine_name": "Core", "next_due_date": "not-a-date"},
            ],
        }
    )

    _items, _doc_name, _pet_name, metadata = _validate_extraction_json(raw)

    assert metadata["vaccination_details"][0]["next_due_date"] == "2026-05-06"
    assert metadata["vaccination_details"][1]["next_due_date"] is None


def test_pet_name_matching_accepts_alias_style_extraction() -> None:
    assert _pet_name_matches_document_name("VEER / ZAYN", "Zayn") is True


def test_select_best_doctor_name_prefers_vaccination_administered_by() -> None:
    selected = _select_best_doctor_name(
        metadata_doctor_name="Owner Name",
        extracted_items=[{"doctor_name": "C/O Ashita Arora"}],
        vaccination_details=[{"administered_by": "Dr. D. P. Chaudhari"}],
        pet_name="Zayn",
    )

    assert selected == "Dr. D. P. Chaudhari"
