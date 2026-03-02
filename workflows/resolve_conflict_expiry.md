# Workflow: Resolve Conflict Expiry

## Objective

Automatically resolve any pending conflicts that have exceeded the 5-day response window. Ensures no conflict remains unresolved indefinitely by defaulting to `KEEP_EXISTING`.

## Trigger

Daily scheduled job (runs alongside the reminder cron via GitHub Actions).

## Required Inputs

- Current date/time (IST)
- Conflicts table with `PENDING` status records

## Steps

1. **Query expired conflicts**
   - Select all records from `conflicts` table where:
     - Status is `PENDING`
     - Created timestamp is older than 5 days from now
   - Service: `conflict_expiry.py`

2. **Auto-resolve each expired conflict**
   - For each expired conflict:
     - Set status to `AUTO_RESOLVED_EXPIRY`.
     - Set resolution to `KEEP_EXISTING`.
     - Set resolution timestamp to now.
     - Do not modify the existing preventive record (it stays as-is).
     - Discard the new extracted data (it was never applied).
   - Use explicit database transactions. Each conflict resolved independently.
   - Service: `conflict_expiry.py`

3. **Log each resolution**
   - For each auto-resolved conflict, log:
     - Conflict ID
     - Pet ID
     - Preventive type
     - Resolution method: `AUTO_RESOLVED_EXPIRY`
     - Timestamp
   - Logging must not block the resolution loop.
   - Service: `conflict_expiry.py`

4. **Notify user (optional)**
   - Send a WhatsApp message informing the user that a conflict was auto-resolved.
   - Include: pet name, preventive type, the date that was kept.
   - If send fails, log and continue. Do not retry.
   - Service: `whatsapp_sender.py`

## Expected Output

- All conflicts older than 5 days resolved as `AUTO_RESOLVED_EXPIRY` with `KEEP_EXISTING`.
- Existing preventive records unchanged.
- Resolution logged for each conflict.
- User optionally notified.

## Edge Cases

- **No expired conflicts:** Job completes with zero actions. Log that the run executed with no results.
- **Conflict's pet was deleted:** Mark conflict as `RESOLVED_PET_DELETED`. Do not notify.
- **DB transaction failure on one conflict:** Log error, continue processing remaining conflicts. Do not halt batch.
- **WhatsApp notification fails:** Log failure. Resolution stands regardless of notification delivery.
- **Cron fires multiple times:** Resolved conflicts have status `AUTO_RESOLVED_EXPIRY` and are not selected again. Idempotent.
- **Conflict created exactly 5 days ago:** Use strict "older than 5 days" (> 120 hours from creation). Borderline cases wait until the next run.
