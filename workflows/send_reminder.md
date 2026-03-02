# Workflow: Send Reminder

## Objective

Send timely WhatsApp reminders to pet parents for upcoming or overdue preventive health events. Runs as a stateless daily cron job with no duplicate sends.

## Trigger

GitHub Actions cron job fires daily at **8:00 AM IST** (Asia/Kolkata).

## Required Inputs

- Current date (server-side, IST)
- Preventive records with `next_due_date` values
- Reminder state from `reminders` table

## Steps

1. **Query due preventive items**
   - Fetch all `preventive_records` where `next_due_date` falls within the reminder window:
     - **Upcoming:** 7 days before due date
     - **Due today:** Exact match
     - **Overdue:** Past due date, not yet completed
   - Service: `reminder_engine.py`

2. **Check for duplicates**
   - For each candidate reminder, check `reminders` table.
   - Skip if a reminder of the same type was already sent for this pet + preventive type + due date within the current reminder cycle.
   - Deduplication enforced at DB level via unique constraints.
   - Service: `reminder_engine.py`

3. **Determine reminder type**
   - **Upcoming (7 days out):** Gentle reminder template.
   - **Due today:** Urgent reminder template.
   - **Overdue (1-14 days):** Overdue template.
   - **Overdue (15+ days):** Nudge template with stronger language.
   - Service: `reminder_engine.py`

4. **Send WhatsApp template message**
   - Use approved WhatsApp template for the reminder type.
   - Include: pet name, preventive type, due date.
   - Include interactive buttons: `REMINDER_DONE`, `REMINDER_SNOOZE`, `REMINDER_RESCHEDULE`.
   - Template names loaded from environment variables, not hardcoded.
   - Service: `whatsapp_sender.py`

5. **Record reminder sent**
   - Insert into `reminders` table:
     - Pet ID, preventive type, due date, reminder type, sent timestamp, status `SENT`.
   - Service: `reminder_engine.py`

6. **Handle send failures**
   - If WhatsApp send fails, retry once.
   - If retry fails, log the failure with error details. Do not block remaining reminders.
   - Service: `reminder_engine.py`, `whatsapp_sender.py`

7. **Log activity**
   - Log each reminder sent in `message_logs`.
   - Logging must not block the reminder flow.
   - Service: `reminder_engine.py`

## Expected Output

- All eligible reminders sent for the day.
- `reminders` table updated with sent records.
- No duplicate reminders.
- Failures logged but do not halt the batch.

## Edge Cases

- **No items due:** Job completes with zero sends. Log that the run executed with no results.
- **User has multiple pets with items due:** Send one reminder per pet per preventive type. Do not batch into a single message.
- **Rate limiting (20 msgs/min per number):** Respect rolling window. Queue excess messages with delay.
- **WhatsApp API downtime:** Retry once per message. Log failures. Next day's run will pick up anything still due.
- **Pet deleted after query but before send:** Check pet still exists before sending. Skip if deleted.
- **Cron fires multiple times:** Deduplication in `reminders` table prevents duplicate sends.
- **Timezone edge:** All date comparisons use `Asia/Kolkata`. Never use server-local or UTC without conversion.
