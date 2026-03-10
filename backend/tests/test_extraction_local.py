"""
Local GPT Extraction Test — runs against fixtures/sample_reports.

Tests both:
    - Image files (JPEG/PNG) → GPT vision API
    - PDF files → PyPDF2 text extraction → GPT text API

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


async def test_extraction():
    """Run GPT extraction on all fixture files and report results."""
    from app.utils.file_reader import encode_image_base64, extract_pdf_text
    from app.services.gpt_extraction import (
        _call_openai_extraction,
        _call_openai_extraction_vision,
        _validate_extraction_json,
    )

    fixtures_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "fixtures", "sample_reports",
    )

    if not os.path.exists(fixtures_dir):
        print(f"ERROR: Fixtures directory not found: {fixtures_dir}")
        return

    files = sorted(os.listdir(fixtures_dir))
    print(f"\n{'='*80}")
    print(f"GPT Extraction Test — {len(files)} files in fixtures/sample_reports")
    print(f"{'='*80}\n")

    results = []

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
                    print(f"  SKIP: Scanned PDF with no extractable text")
                    results.append({
                        "file": filename,
                        "status": "skipped",
                        "reason": "scanned PDF (no text)",
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
                items, doc_name, pet_name, _metadata = _validate_extraction_json(raw_json)
                print(f"  Document name: {doc_name}")
                print(f"  Pet name: {pet_name}")
                print(f"  Items extracted: {len(items)}")
                for item in items:
                    print(f"    - {item.get('item_name')}: {item.get('last_done_date')}")
                print(f"  Time: {elapsed:.1f}s")

                results.append({
                    "file": filename,
                    "status": "success",
                    "document_name": doc_name,
                    "pet_name": pet_name,
                    "items_count": len(items),
                    "items": items,
                    "time_s": round(elapsed, 1),
                })
            except ValueError as ve:
                print(f"  VALIDATION ERROR: {ve}")
                print(f"  Raw JSON: {raw_json[:200]}")
                results.append({
                    "file": filename,
                    "status": "validation_error",
                    "error": str(ve),
                    "time_s": round(elapsed, 1),
                })
        elif error:
            results.append({
                "file": filename,
                "status": "error",
                "error": error,
                "time_s": round(elapsed, 1),
            })
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
    total_time = sum(r.get("time_s", 0) for r in results)
    print(f"\nTotal items extracted: {total_items}")
    print(f"Total time: {total_time:.1f}s")

    if success:
        print(f"\n--- Successful Extractions ---")
        for r in success:
            items_str = ", ".join(
                f"{i['item_name']} ({i['last_done_date']})"
                for i in r.get("items", [])
            ) or "(no preventive items)"
            print(f"  {r['file']}: {r['items_count']} items — {items_str}")

    if failed:
        print(f"\n--- Failed Extractions ---")
        for r in failed:
            print(f"  {r['file']}: {r.get('error', 'unknown')}")

    if skipped:
        print(f"\n--- Skipped ---")
        for r in skipped:
            print(f"  {r['file']}: {r.get('reason', 'unknown')}")

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
