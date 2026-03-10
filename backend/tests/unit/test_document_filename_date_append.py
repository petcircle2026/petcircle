from app.services.gpt_extraction import _append_single_extracted_date_to_filename


def test_appends_single_unique_date_before_extension() -> None:
    result = _append_single_extracted_date_to_filename(
        "vaccination_record.pdf",
        [{"last_done_date": "2026-03-10"}],
    )
    assert result == "vaccination_record_2026-03-10.pdf"


def test_keeps_original_when_multiple_dates_present() -> None:
    result = _append_single_extracted_date_to_filename(
        "vaccination_record.pdf",
        [
            {"last_done_date": "2026-03-10"},
            {"last_done_date": "2026-04-10"},
        ],
    )
    assert result == "vaccination_record.pdf"


def test_keeps_original_when_date_already_present() -> None:
    result = _append_single_extracted_date_to_filename(
        "vaccination_record_2026-03-10.pdf",
        [{"last_done_date": "2026-03-10"}],
    )
    assert result == "vaccination_record_2026-03-10.pdf"
