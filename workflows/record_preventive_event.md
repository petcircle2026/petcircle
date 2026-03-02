# Workflow: Record Preventive Event

## Objective

Process an uploaded health document, extract structured preventive health data using GPT, create or update a preventive record, and trigger conflict detection if the extracted data conflicts with existing records.

## Trigger

User uploads a document (photo or PDF) via WhatsApp for a registered pet.

## Required Inputs

- Authenticated user (phone number matched in `users` table)
- Active pet record (user must have at least one pet)
- Uploaded file (from WhatsApp media)

## Steps

1. **Receive and validate document**
   - Download media from WhatsApp using media ID from webhook payload.
   - Validate MIME type: `image/jpeg`, `image/png`, `application/pdf`.
   - Validate file size: max 10 MB.
   - Check daily upload limit: max 10 uploads per pet per day.
   - If validation fails, inform user and stop.
   - Service: `document_upload.py`

2. **Store document**
   - Upload to Supabase storage bucket `petcircle-documents`.
   - Path: `{user_id}/{pet_id}/{filename}`.
   - No public URLs. Access via signed URLs only.
   - Insert record into `documents` table with metadata.
   - Service: `document_upload.py`

3. **Extract structured data via GPT**
   - Send document to OpenAI GPT (`gpt-4.1`) for extraction.
   - Expected output (strict JSON):
     - Preventive type (vaccine, deworming, tick treatment, etc.)
     - Product/vaccine name
     - Date administered
     - Next due date (if present)
     - Vet name (if present)
     - Notes
   - Wrap GPT call with retry policy.
   - Service: `gpt_extraction.py`

4. **Validate extracted data**
   - Confirm required fields are present (type, name, date).
   - Parse dates into `YYYY-MM-DD` format.
   - If extraction fails or returns incomplete data, log the failure and inform user.
   - Service: `gpt_extraction.py`

5. **Calculate next due date**
   - If GPT did not extract a next due date, calculate from the preventive master schedule.
   - Look up the preventive type in the frozen master table.
   - Apply species-specific interval to the administered date.
   - Service: `preventive_calculator.py`

6. **Check for conflicts**
   - Query existing preventive records for the same pet and preventive type.
   - If an existing record has a different date for the same event, trigger conflict flow.
   - If no conflict, proceed to create/update.
   - Service: `conflict_engine.py`

7. **Create or update preventive record**
   - Insert into `preventive_records` table.
   - Enforce uniqueness constraints.
   - Link to the source document.
   - Service: `preventive_calculator.py`

8. **Confirm to user**
   - Send WhatsApp message confirming what was recorded.
   - Include: preventive type, date, next due date.
   - Service: `whatsapp_sender.py`

## Expected Output

- Document stored in Supabase bucket.
- `documents` table record created.
- GPT extraction logged.
- `preventive_records` entry created or updated.
- Conflict created (if applicable).
- User receives confirmation message.

## Edge Cases

- **Unsupported file type:** Reject with message listing accepted types.
- **File exceeds 10 MB:** Reject with size limit message.
- **Daily upload limit exceeded:** Inform user of the 10/day/pet limit.
- **GPT extraction fails:** Log error. Inform user document could not be processed. Do not create partial records.
- **GPT returns ambiguous data:** Flag for manual review. Do not auto-create record.
- **Conflict detected:** Do not overwrite. Trigger `handle_conflict` workflow.
- **User has multiple pets:** Ask which pet the document is for before processing.
- **Duplicate document:** Detect via hash or metadata. Inform user and skip.
