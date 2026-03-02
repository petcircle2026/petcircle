# Workflow: Handle Conflict

## Objective

When GPT-extracted preventive data conflicts with an existing record, present the user with a clear choice and resolve the conflict based on their decision. If no response is received within 5 days, auto-resolve by keeping the existing record.

## Trigger

The conflict engine detects a date discrepancy between a newly extracted preventive event and an existing record for the same pet and preventive type.

## Required Inputs

- Pet ID
- Preventive type (e.g., Rabies vaccine)
- Existing record details (date, source)
- New extracted details (date, source document)

## Steps

1. **Create conflict record**
   - Insert into `conflicts` table with:
     - Pet ID
     - Preventive type
     - Existing date and record ID
     - New extracted date and document ID
     - Status: `PENDING`
     - Created timestamp
   - Service: `conflict_engine.py`

2. **Send interactive message to user**
   - Send WhatsApp interactive message with two buttons:
     - `CONFLICT_USE_NEW` — "Use new date"
     - `CONFLICT_KEEP_EXISTING` — "Keep existing date"
   - Message body includes: pet name, preventive type, both dates clearly labeled.
   - Button payload IDs must not be hardcoded in service logic; load from constants.
   - Service: `whatsapp_sender.py`

3. **Wait for user response**
   - On button click, webhook receives the payload ID.
   - Match payload to the pending conflict for this user/pet.

4. **Resolve based on user choice**
   - **USE_NEW:** Update `preventive_records` with the new date. Recalculate next due date. Mark conflict as `RESOLVED_USE_NEW`.
   - **KEEP_EXISTING:** Keep current record unchanged. Mark conflict as `RESOLVED_KEEP_EXISTING`.
   - Update conflict record with resolution timestamp and method.
   - Service: `conflict_engine.py`, `preventive_calculator.py`

5. **Confirm resolution**
   - Send WhatsApp message confirming which date was kept.
   - Service: `whatsapp_sender.py`

6. **Log activity**
   - Log the conflict creation, user decision, and resolution in `message_logs`.
   - Service: `conflict_engine.py`

## Expected Output

- `conflicts` table record created and eventually resolved.
- `preventive_records` updated (if USE_NEW chosen).
- User receives confirmation of resolution.

## Edge Cases

- **No response within 5 days:** Auto-resolve with `KEEP_EXISTING`. Log as `AUTO_RESOLVED_EXPIRY`. See `resolve_conflict_expiry.md`.
- **User sends text instead of clicking button:** Re-send the interactive message. Do not parse free text as a decision.
- **Multiple pending conflicts for same user:** Each conflict is independent. Present and resolve separately.
- **Conflict for a pet that was deleted:** Mark conflict as `RESOLVED_PET_DELETED`. Do not send message.
- **WhatsApp delivery failure:** Retry once. If still fails, log and let expiry handle it.
