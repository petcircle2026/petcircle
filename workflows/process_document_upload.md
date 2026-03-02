# Workflow: Process Document Upload

## Objective

Handle the full lifecycle of a document uploaded via WhatsApp: download from WhatsApp servers, validate, store in Supabase, extract structured health data via GPT, and persist results.

## Trigger

Webhook receives a message of type `image` or `document` from a registered user.

## Required Inputs

- WhatsApp media ID (from webhook payload)
- User ID (resolved from phone number)
- Pet ID (resolved from conversation context or user selection)
- MIME type (from webhook payload)

## Steps

1. **Download media from WhatsApp**
   - Use the media ID to fetch the download URL from WhatsApp Cloud API.
   - Download the binary content.
   - Service: `document_upload.py`

2. **Validate MIME type**
   - Accepted types: `image/jpeg`, `image/png`, `application/pdf`.
   - If rejected, send user a message listing accepted formats and stop.
   - Service: `document_upload.py`

3. **Validate file size**
   - Maximum: 10 MB.
   - If exceeded, inform user and stop.
   - Service: `document_upload.py`

4. **Check daily upload limit**
   - Query `documents` table for uploads by this pet today.
   - Maximum: 10 uploads per pet per day.
   - If exceeded, inform user and stop.
   - Service: `document_upload.py`

5. **Determine target pet**
   - If user has one pet, auto-select.
   - If user has multiple pets, check conversation context for a selected pet.
   - If ambiguous, ask user which pet the document is for before proceeding.
   - Service: `document_upload.py`

6. **Upload to Supabase storage**
   - Bucket: `petcircle-documents` (private).
   - Path: `{user_id}/{pet_id}/{filename}`.
   - Generate a unique filename to avoid collisions (e.g., UUID prefix).
   - No public URLs. All access via signed URLs with expiry.
   - Service: `document_upload.py`

7. **Create document record**
   - Insert into `documents` table:
     - User ID, Pet ID, original filename, storage path, MIME type, file size, upload timestamp.
   - Service: `document_upload.py`

8. **Trigger GPT extraction**
   - Send the stored document to OpenAI GPT (`gpt-4.1`).
   - Prompt requests strict JSON output:
     - Preventive type
     - Product/vaccine name
     - Date administered
     - Next due date (if present)
     - Vet name (if present)
     - Notes
   - Apply retry policy: retry once on failure.
   - Service: `gpt_extraction.py`

9. **Validate extraction results**
   - Confirm required fields: type, name, date.
   - Parse all dates to `YYYY-MM-DD`.
   - If extraction is incomplete or fails, log the error and inform user that the document could not be processed automatically.
   - Service: `gpt_extraction.py`

10. **Store extraction results**
    - Link extracted data to the document record.
    - Proceed to preventive record creation (see `record_preventive_event.md`).
    - Service: `gpt_extraction.py`

## Expected Output

- File stored in Supabase private bucket.
- `documents` record created.
- GPT extraction completed and logged.
- Extracted data handed off to preventive record workflow.
- User informed of success or failure.

## Edge Cases

- **WhatsApp media download fails:** Retry once. If still fails, inform user to re-upload.
- **Corrupt or unreadable file:** GPT extraction will fail. Log and inform user.
- **GPT returns non-JSON or malformed JSON:** Parse error caught. Log raw response. Inform user.
- **GPT timeout:** Retry once with same payload. Log both attempts.
- **Multiple documents in single message:** Process each separately. Apply upload limit per document.
- **Storage upload fails:** Do not proceed to extraction. Retry once. Log failure.
- **Ambiguous pet selection:** Do not guess. Ask user explicitly.
- **User sends document before onboarding:** Reject. Prompt to complete onboarding first.
