# Workflow: Handle Reminder Response

## Objective

Process the user's response to a preventive health reminder. Update the preventive record and reminder state based on the chosen action: mark as done, snooze, reschedule, or cancel.

## Trigger

User clicks an interactive button on a reminder message received via WhatsApp. The webhook receives a button payload.

## Required Inputs

- Button payload ID (from webhook)
- User ID (from phone number)
- Linked reminder record (matched via payload context)
- Associated preventive record

## Steps

1. **Identify the reminder**
   - Match the incoming button payload to a `SENT` reminder in the `reminders` table.
   - Resolve the linked pet and preventive record.
   - If no matching reminder is found, ignore the payload and log a warning.
   - Service: `reminder_response.py`

2. **Process based on action**

   **REMINDER_DONE — Mark as completed**
   - Update the preventive record: set status to `COMPLETED`, record completion date as today.
   - Recalculate `next_due_date` using the preventive master schedule and the completion date.
   - Create a new preventive record for the next cycle if applicable.
   - Update reminder status to `COMPLETED`.
   - Service: `reminder_response.py`, `preventive_calculator.py`

   **REMINDER_SNOOZE — Postpone 7 days**
   - Push the reminder by 7 days.
   - Update `next_due_date` on the preventive record to current due date + 7 days.
   - Update reminder status to `SNOOZED`.
   - A new reminder will be picked up by the daily cron on the new date.
   - Service: `reminder_response.py`

   **REMINDER_RESCHEDULE — Enter a new date**
   - Send a WhatsApp message asking the user to provide a new date.
   - Wait for the user's text reply.
   - Validate the date (accepted formats: DD/MM/YYYY, DD-MM-YYYY, 12 March 2024, ISO).
   - Update `next_due_date` on the preventive record.
   - Update reminder status to `RESCHEDULED`.
   - Service: `reminder_response.py`, `preventive_calculator.py`

   **REMINDER_CANCEL — Cancel the reminder**
   - Mark the reminder as `CANCELLED`.
   - Do not change the preventive record.
   - No further reminders for this specific due date.
   - Service: `reminder_response.py`

3. **Confirm to user**
   - Send a WhatsApp message confirming the action taken.
   - Include: pet name, preventive type, and the resulting state (completed, new date, cancelled).
   - Service: `whatsapp_sender.py`

4. **Log activity**
   - Log the button click, action taken, and confirmation sent.
   - Service: `reminder_response.py`

## Expected Output

- Reminder record updated with final status.
- Preventive record updated (if DONE, SNOOZE, or RESCHEDULE).
- Next due date recalculated (if DONE or RESCHEDULE).
- User receives confirmation.

## Edge Cases

- **User clicks button on an already-resolved reminder:** Inform user it has already been handled. Do not re-process.
- **Invalid date on reschedule:** Re-prompt with accepted formats. Allow up to 2 retries, then cancel the reschedule.
- **Date in the past on reschedule:** Reject. Ask for a future date.
- **User sends text instead of clicking button:** Do not interpret free text as an action. Re-send the interactive message if context matches a pending reminder.
- **Reminder record not found for payload:** Log warning. Ignore silently (do not error to user).
- **Snooze limit:** No hard limit in Phase 1, but log snooze count for analytics.
