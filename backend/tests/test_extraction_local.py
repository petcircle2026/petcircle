"""
Local GPT Extraction Test — runs against Sample_Reports.

Tests:
    - Image files (JPEG/PNG) → GPT vision API
    - PDF files → PyPDF2 text extraction → GPT text API
    - Scanned PDFs → PyMuPDF render → GPT vision fallback
    - Diagnostic values extraction (CBC, urine parameters)
    - Vaccination detail extraction (doses, batch numbers, next due dates)
    - Prescription extraction
    - Query engine scenarios against extracted data

Usage:
    cd backend
    set APP_ENV=production
    python -m tests.test_extraction_local

    Or with a specific API key:
    set OPENAI_API_KEY=sk-your-key
    python -m tests.test_extraction_local

Requires OPENAI_API_KEY in environment or env file.
"""

import asyncio
import os
import sys
import json
import time

# Add backend to path so imports work.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Must set APP_ENV before importing app modules.
os.environ.setdefault("APP_ENV", "production")


# --- Expected extraction outcomes per file ---
# Used to validate that GPT extraction produces the right structure.
EXPECTED_OUTCOMES = {
    # Blood reports: should extract Preventive Blood Test + diagnostic values
    "Blood_28_01_25.pdf": {
        "category": "Diagnostic",
        "expected_items": ["Preventive Blood Test"],
        "expected_date_prefix": "2025-01-28",
        "must_have_diagnostic_values": True,
        "expected_test_type": "blood",
    },
    "Blood_29_01_25.pdf": {
        "category": "Diagnostic",
        "expected_items": ["Preventive Blood Test"],
        "expected_date_prefix": "2025-01-29",
        "must_have_diagnostic_values": True,
        "expected_test_type": "blood",
    },
    "Blood_29_01_25_2.pdf": {
        "category": "Diagnostic",
        "expected_items": ["Preventive Blood Test"],
        "expected_date_prefix": "2025-01-29",
        "must_have_diagnostic_values": True,
        "expected_test_type": "blood",
    },
    "Blood _29_01_25_3.pdf": {
        "category": "Diagnostic",
        "expected_items": ["Preventive Blood Test"],
        "expected_date_prefix": "2025-01-29",
        "must_have_diagnostic_values": True,
        "expected_test_type": "blood",
    },
    "Blood_12_02_25_2.pdf": {
        "category": "Diagnostic",
        "expected_items": ["Preventive Blood Test"],
        "expected_date_prefix": "2025-02-12",
        "must_have_diagnostic_values": True,
        "expected_test_type": "blood",
    },
    "Blood_12_02_25_3.pdf": {
        "category": "Diagnostic",
        "expected_items": ["Preventive Blood Test"],
        "expected_date_prefix": "2025-02-12",
        "must_have_diagnostic_values": True,
        "expected_test_type": "blood",
    },
    "Blood_22_02_25_1.pdf": {
        "category": "Diagnostic",
        "expected_items": ["Preventive Blood Test"],
        "expected_date_prefix": "2025-02-22",
        "must_have_diagnostic_values": True,
        "expected_test_type": "blood",
    },
    "Blood_22_02_25_2.pdf": {
        "category": "Diagnostic",
        "expected_items": ["Preventive Blood Test"],
        "expected_date_prefix": "2025-02-22",
        "must_have_diagnostic_values": True,
        "expected_test_type": "blood",
    },
    "Blood_22_02_25_3.pdf": {
        "category": "Diagnostic",
        "expected_items": ["Preventive Blood Test"],
        "expected_date_prefix": "2025-02-22",
        "must_have_diagnostic_values": True,
        "expected_test_type": "blood",
    },
    "CBC_12_02_25.pdf": {
        "category": "Diagnostic",
        "expected_items": ["Preventive Blood Test"],
        "expected_date_prefix": "2025-02-12",
        "must_have_diagnostic_values": True,
        "expected_test_type": "blood",
    },
    # Urine reports: should extract diagnostic values but no tracked preventive item
    "Urine_28_11_24.pdf": {
        "category": "Diagnostic",
        "expected_items": [],
        "must_have_diagnostic_values": True,
        "expected_test_type": "urine",
    },
    "Urine_culture_29_11_24.pdf": {
        "category": "Diagnostic",
        "expected_items": [],
        "must_have_diagnostic_values": True,
        "expected_test_type": "urine",
    },
    "Urine_1_02_25.pdf": {
        "category": "Diagnostic",
        "expected_items": [],
        "must_have_diagnostic_values": True,
        "expected_test_type": "urine",
    },
    "Urine_12_02_25.pdf": {
        "category": "Diagnostic",
        "expected_items": [],
        "must_have_diagnostic_values": True,
        "expected_test_type": "urine",
    },
    "Urine_26_02_25.pdf": {
        "category": "Diagnostic",
        "expected_items": [],
        "must_have_diagnostic_values": True,
        "expected_test_type": "urine",
    },
    # Prescription
    "Prescription_Chavan_12_02_25.jpg": {
        "category": "Prescription",
        "expected_items": [],  # Prescriptions may or may not have tracked items
        "must_have_diagnostic_values": False,
    },
    # Vaccination records
    "Zayn_Vaccination_Record.jpg": {
        "category": "Vaccination",
        "expected_items": ["Rabies Vaccine", "Core Vaccine"],
        "must_have_vaccination_details": True,
        "must_have_diagnostic_values": False,
    },
    "Zayn_Vaccination_Record_1.jpg": {
        "category": "Vaccination",
        "expected_items": ["Rabies Vaccine", "Core Vaccine"],
        "must_have_vaccination_details": True,
        "must_have_diagnostic_values": False,
    },
    "Zayn_Vaccination_Record_2.jpg": {
        "category": "Vaccination",
        "expected_items": ["Rabies Vaccine", "Core Vaccine"],
        "must_have_vaccination_details": True,
        "must_have_diagnostic_values": False,
    },
}


def _print_diagnostic_values(diagnostic_values: list[dict], indent: str = "    ") -> None:
    """Pretty-print diagnostic test values."""
    if not diagnostic_values:
        print(f"{indent}(none)")
        return

    # Group by test_type.
    by_type: dict[str, list[dict]] = {}
    for val in diagnostic_values:
        if not isinstance(val, dict):
            continue
        tt = str(val.get("test_type", "unknown")).strip().lower()
        by_type.setdefault(tt, []).append(val)

    for test_type, values in sorted(by_type.items()):
        print(f"{indent}[{test_type.upper()}] — {len(values)} parameters:")
        for val in values:
            name = val.get("parameter_name", "?")
            numeric = val.get("value_numeric")
            text = val.get("value_text")
            unit = val.get("unit", "")
            ref = val.get("reference_range", "")
            flag = val.get("status_flag", "")
            obs = val.get("observed_at", "")

            value_str = str(numeric) if numeric is not None else (str(text) if text else "N/A")
            parts = [f"{name}: {value_str}"]
            if unit:
                parts.append(f"{unit}")
            if ref:
                parts.append(f"ref={ref}")
            if flag:
                parts.append(f"[{flag.upper()}]")
            if obs:
                parts.append(f"on {obs}")
            print(f"{indent}  - {' '.join(parts)}")


def _print_vaccination_details(vaccination_details: list[dict], indent: str = "    ") -> None:
    """Pretty-print vaccination detail rows."""
    if not vaccination_details:
        print(f"{indent}(none)")
        return

    for detail in vaccination_details:
        if not isinstance(detail, dict):
            continue
        name = detail.get("vaccine_name") or detail.get("vaccine_name_raw") or "?"
        batch = detail.get("batch_number", "")
        next_due = detail.get("next_due_date", "")
        admin_by = detail.get("administered_by", "")
        dose = detail.get("dose", "")
        route = detail.get("route", "")
        mfr = detail.get("manufacturer", "")

        parts = [name]
        if batch:
            parts.append(f"batch={batch}")
        if next_due:
            parts.append(f"next_due={next_due}")
        if admin_by:
            parts.append(f"by={admin_by}")
        if dose:
            parts.append(f"dose={dose}")
        if route:
            parts.append(f"route={route}")
        if mfr:
            parts.append(f"mfr={mfr}")
        print(f"{indent}  - {' | '.join(parts)}")


def _validate_result(filename: str, result: dict) -> list[str]:
    """Validate extraction result against expected outcomes. Returns list of issues."""
    issues = []
    expected = EXPECTED_OUTCOMES.get(filename)
    if not expected:
        return issues  # No expectations defined.

    if result.get("status") != "success":
        issues.append(f"FAIL: Expected success but got {result.get('status')}: {result.get('error', '')}")
        return issues

    # Category check.
    actual_category = result.get("document_category", "")
    if expected.get("category") and actual_category != expected["category"]:
        issues.append(f"CATEGORY: expected '{expected['category']}' got '{actual_category}'")

    # Items check.
    actual_item_names = [i.get("item_name", "") for i in result.get("items", [])]
    for expected_item in expected.get("expected_items", []):
        if not any(expected_item.lower() in name.lower() for name in actual_item_names):
            issues.append(f"MISSING ITEM: expected '{expected_item}' in items")

    # Date prefix check.
    if expected.get("expected_date_prefix"):
        dates = [i.get("last_done_date", "") for i in result.get("items", [])]
        if dates and not any(d.startswith(expected["expected_date_prefix"]) for d in dates):
            issues.append(f"DATE: expected date starting with '{expected['expected_date_prefix']}', got {dates}")

    # Diagnostic values check.
    diag_values = result.get("diagnostic_values", [])
    if expected.get("must_have_diagnostic_values"):
        if not diag_values:
            issues.append("MISSING: No diagnostic_values extracted (expected blood/urine parameters)")
        else:
            expected_type = expected.get("expected_test_type")
            if expected_type:
                actual_types = {str(v.get("test_type", "")).lower() for v in diag_values if isinstance(v, dict)}
                if expected_type not in actual_types:
                    issues.append(f"TEST_TYPE: expected '{expected_type}' in diagnostic_values, got {actual_types}")

    # Vaccination details check.
    vacc_details = result.get("vaccination_details", [])
    if expected.get("must_have_vaccination_details") and not vacc_details:
        issues.append("MISSING: No vaccination_details extracted (expected vaccine rows)")

    return issues


async def test_extraction():
    """Run GPT extraction on all fixture files and report results."""
    from app.utils.file_reader import encode_image_base64, extract_pdf_text, render_pdf_pages_as_images
    from app.services.gpt_extraction import (
        _call_openai_extraction,
        _call_openai_extraction_vision,
        _validate_extraction_json,
    )

    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    candidate_dirs = [
        os.path.join(repo_root, "Sample_Reports"),
        os.path.join(repo_root, "fixtures", "sample_reports"),
    ]
    fixtures_dir = next((path for path in candidate_dirs if os.path.exists(path)), candidate_dirs[0])

    if not os.path.exists(fixtures_dir):
        print(f"ERROR: Fixtures directory not found: {fixtures_dir}")
        return

    files = sorted(os.listdir(fixtures_dir))
    print(f"\n{'='*80}")
    print(f"GPT Extraction Test — {len(files)} files in {os.path.relpath(fixtures_dir, repo_root)}")
    print(f"{'='*80}\n")

    results = []
    all_issues = []

    for filename in files:
        filepath = os.path.join(fixtures_dir, filename)
        if not os.path.isfile(filepath):
            continue

        file_size = os.path.getsize(filepath)
        ext = filename.lower().rsplit(".", 1)[-1]

        print(f"--- {filename} ({file_size:,} bytes) ---")

        with open(filepath, "rb") as f:
            file_bytes = f.read()

        start_time = time.time()
        raw_json = None
        error = None

        try:
            if ext in ("jpg", "jpeg", "png"):
                # Image → vision API
                mime = "image/jpeg" if ext in ("jpg", "jpeg") else "image/png"
                data_uri = encode_image_base64(file_bytes, mime)
                print(f"  Type: Image ({mime}), using vision API")
                raw_json = await _call_openai_extraction_vision(data_uri)

            elif ext == "pdf":
                # PDF → text extraction first
                pdf_text = extract_pdf_text(file_bytes)
                text_len = len(pdf_text.strip())
                print(f"  Type: PDF, extracted text: {text_len} chars")

                if text_len > 20:
                    raw_json = await _call_openai_extraction(
                        f"Veterinary document text:\n\n{pdf_text}"
                    )
                else:
                    # Scanned PDF — try vision fallback.
                    print(f"  Scanned PDF — trying vision fallback...")
                    page_images = render_pdf_pages_as_images(file_bytes, max_pages=3)
                    if page_images:
                        print(f"  Rendered {len(page_images)} page(s) as images")
                        raw_json = await _call_openai_extraction_vision(page_images[0])
                    else:
                        print(f"  SKIP: Cannot render scanned PDF (PyMuPDF not available?)")
                        results.append({
                            "file": filename,
                            "status": "skipped",
                            "reason": "scanned PDF (no text, no vision fallback)",
                            "time_s": 0,
                        })
                        print()
                        continue
            else:
                print(f"  SKIP: Unsupported file type")
                continue

        except Exception as e:
            error = str(e)
            print(f"  ERROR: {error}")

        elapsed = time.time() - start_time

        if raw_json:
            try:
                items, doc_name, pet_name, metadata = _validate_extraction_json(raw_json)
                diagnostic_values = metadata.get("diagnostic_values", [])
                vaccination_details = metadata.get("vaccination_details", [])
                document_category = metadata.get("document_category")

                print(f"  Document name: {doc_name}")
                print(f"  Document category: {document_category}")
                print(f"  Document type: {metadata.get('document_type')}")
                print(f"  Pet name: {pet_name}")
                print(f"  Doctor: {metadata.get('doctor_name')}")
                print(f"  Clinic: {metadata.get('clinic_name')}")

                # Preventive items.
                print(f"  Preventive items: {len(items)}")
                for item in items:
                    parts = [f"{item.get('item_name')}: {item.get('last_done_date')}"]
                    if item.get("dose"):
                        parts.append(f"dose={item['dose']}")
                    if item.get("batch_number"):
                        parts.append(f"batch={item['batch_number']}")
                    if item.get("doctor_name"):
                        parts.append(f"dr={item['doctor_name']}")
                    print(f"    - {' | '.join(parts)}")

                # Diagnostic values.
                if diagnostic_values:
                    print(f"  Diagnostic values: {len(diagnostic_values)} parameters")
                    _print_diagnostic_values(diagnostic_values)

                # Diagnostic summary.
                diag_summary = metadata.get("diagnostic_summary")
                if diag_summary:
                    print(f"  Diagnostic summary: {diag_summary[:150]}...")

                # Vaccination details.
                if vaccination_details:
                    print(f"  Vaccination details: {len(vaccination_details)} rows")
                    _print_vaccination_details(vaccination_details)

                print(f"  Time: {elapsed:.1f}s")

                result_entry = {
                    "file": filename,
                    "status": "success",
                    "document_name": doc_name,
                    "document_category": document_category,
                    "document_type": metadata.get("document_type"),
                    "pet_name": pet_name,
                    "items_count": len(items),
                    "items": items,
                    "doctor_name": metadata.get("doctor_name"),
                    "clinic_name": metadata.get("clinic_name"),
                    "diagnostic_summary": diag_summary,
                    "diagnostic_values_count": len(diagnostic_values),
                    "diagnostic_values": diagnostic_values,
                    "vaccination_details_count": len(vaccination_details),
                    "vaccination_details": vaccination_details,
                    "time_s": round(elapsed, 1),
                }
                results.append(result_entry)

                # Validate against expectations.
                file_issues = _validate_result(filename, result_entry)
                if file_issues:
                    print(f"  ISSUES:")
                    for issue in file_issues:
                        print(f"    ! {issue}")
                    all_issues.extend([(filename, issue) for issue in file_issues])
                else:
                    print(f"  VALIDATION: PASS")

            except ValueError as ve:
                print(f"  VALIDATION ERROR: {ve}")
                print(f"  Raw JSON length: {len(raw_json)} chars")
                print(f"  Raw JSON tail: ...{raw_json[-200:]}")
                results.append({
                    "file": filename,
                    "status": "validation_error",
                    "error": str(ve),
                    "raw_json_length": len(raw_json),
                    "time_s": round(elapsed, 1),
                })
                file_issues = _validate_result(filename, {"status": "validation_error", "error": str(ve)})
                all_issues.extend([(filename, issue) for issue in file_issues])
        elif error:
            results.append({
                "file": filename,
                "status": "error",
                "error": error,
                "time_s": round(elapsed, 1),
            })
            file_issues = _validate_result(filename, {"status": "error", "error": error})
            all_issues.extend([(filename, issue) for issue in file_issues])
        print()

    # --- Summary ---
    print(f"\n{'='*80}")
    print("EXTRACTION TEST SUMMARY")
    print(f"{'='*80}")

    success = [r for r in results if r["status"] == "success"]
    failed = [r for r in results if r["status"] in ("error", "validation_error")]
    skipped = [r for r in results if r["status"] == "skipped"]

    print(f"\nTotal files: {len(results)}")
    print(f"  Success: {len(success)}")
    print(f"  Failed:  {len(failed)}")
    print(f"  Skipped: {len(skipped)}")

    total_items = sum(r.get("items_count", 0) for r in success)
    total_diag = sum(r.get("diagnostic_values_count", 0) for r in success)
    total_vacc = sum(r.get("vaccination_details_count", 0) for r in success)
    total_time = sum(r.get("time_s", 0) for r in results)
    print(f"\nTotal preventive items extracted: {total_items}")
    print(f"Total diagnostic parameters extracted: {total_diag}")
    print(f"Total vaccination detail rows: {total_vacc}")
    print(f"Total time: {total_time:.1f}s")

    # Breakdown by category.
    categories = {}
    for r in success:
        cat = r.get("document_category", "Unknown")
        categories.setdefault(cat, []).append(r["file"])
    print(f"\n--- By Category ---")
    for cat, files_list in sorted(categories.items()):
        print(f"  {cat}: {len(files_list)} files")

    if success:
        print(f"\n--- Successful Extractions ---")
        for r in success:
            items_str = ", ".join(
                f"{i['item_name']} ({i['last_done_date']})"
                for i in r.get("items", [])
            ) or "(no preventive items)"
            diag_str = f", {r['diagnostic_values_count']} diag params" if r.get("diagnostic_values_count") else ""
            vacc_str = f", {r['vaccination_details_count']} vacc rows" if r.get("vaccination_details_count") else ""
            print(f"  {r['file']}: {r['items_count']} items — {items_str}{diag_str}{vacc_str}")

    if failed:
        print(f"\n--- Failed Extractions ---")
        for r in failed:
            print(f"  {r['file']}: {r.get('error', 'unknown')}")

    if skipped:
        print(f"\n--- Skipped ---")
        for r in skipped:
            print(f"  {r['file']}: {r.get('reason', 'unknown')}")

    # Validation issues.
    if all_issues:
        print(f"\n{'='*80}")
        print(f"VALIDATION ISSUES: {len(all_issues)}")
        print(f"{'='*80}")
        for filename, issue in all_issues:
            print(f"  [{filename}] {issue}")
    else:
        print(f"\nALL VALIDATIONS PASSED")

    # Save detailed results to JSON.
    results_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "extraction_test_results.json",
    )
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nDetailed results saved to: {results_path}")


if __name__ == "__main__":
    asyncio.run(test_extraction())
