# PetCircle Phase 1 — Manual Testing Guide

Complete test instructions for WhatsApp flows, Admin Dashboard, and User Dashboard.

**Production WhatsApp Number:** The number linked to `WHATSAPP_PHONE_NUMBER_ID` in your Meta Business account.
**Frontend URL:** https://pet-circle-chi.vercel.app
**Backend URL:** https://pet-circle.onrender.com

---

## Prerequisites

Before testing:
1. Backend is deployed and `/health` returns `{"status":"healthy","timezone":"Asia/Kolkata"}`
2. Frontend is deployed on Vercel
3. WhatsApp Cloud API is configured in Meta Business Manager
4. All 7 WhatsApp templates are approved:
   - `petcircle_reminder_v1`
   - `petcircle_overdue_v1`
   - `petcircle_nudge_v1`
   - `petcircle_conflict_v1`
   - `petcircle_onboarding_complete_v1`
   - `birthday_celebration_v1`
   - `order_fulfillment_check_v1`
5. Webhook URL is set in Meta: `https://pet-circle.onrender.com/webhook/whatsapp`
6. Verify token matches `WHATSAPP_VERIFY_TOKEN` in environment
7. `ORDER_NOTIFICATION_PHONE` is set if you want to verify admin order notifications

---

## Test Flow 1: Complete Onboarding (New User)

**Goal:** Register a new user and pet via WhatsApp conversation.

| Step | You Send | Expected Response | Pass? |
|------|----------|-------------------|-------|
| 1 | `Hello` (first message ever) | Welcome message + consent request: _"Reply yes to continue or no to opt out"_ | |
| 2 | `yes` | _"What is your full name?"_ | |
| 3 | `Rajesh Kumar` | _"What is your pincode? (Type skip if you prefer not to share)"_ | |
| 4 | `110001` | _"What is your pet's name?"_ | |
| 5 | `Buddy` | _"Is Buddy a dog or a cat?"_ | |
| 6 | `dog` | _"What breed is Buddy? (Type skip if you're not sure)"_ | |
| 7 | `Golden Retriever` | _"What is Buddy's gender? (male or female, or skip)"_ | |
| 8 | `male` | _"When was Buddy born? (DD/MM/YYYY or skip)"_ | |
| 9 | `15/03/2020` | _"What is Buddy's weight in kg? (e.g., 12.5, or skip)"_ | |
| 10 | `25.5` | _"Is Buddy neutered/spayed? (yes, no, or skip)"_ | |
| 11 | `yes` | Completion message with dashboard link: `https://pet-circle-chi.vercel.app/dashboard/{token}` | |

**Verify after completion:**
- [ ] Dashboard link works in browser
- [ ] Pet profile shows: Buddy, Dog, Golden Retriever, Male, 15/03/2020, 25.5 kg, Neutered: Yes
- [ ] Health score ring displays (should be 0/100 since no records done yet)
- [ ] 16 preventive items seeded across essential and complementary categories (Rabies Vaccine, Core Vaccine, Deworming, Tick/Flea, Annual Checkup, Preventive Blood Test, Dental Check, Chronic Care, Food Ordering, Nutrition Planning, Supplements, Bath & Grooming, Nail Trimming, Ear Cleaning, Birthday Celebration)
- [ ] All items show status "upcoming" with no last done date

---

## Test Flow 2: Onboarding with Skips

**Goal:** Verify optional fields can be skipped.

| Step | You Send | Expected Response | Pass? |
|------|----------|-------------------|-------|
| 1 | `Hi` (from new number) | Welcome + consent request | |
| 2 | `yes` | Name request | |
| 3 | `Priya Sharma` | Pincode request | |
| 4 | `skip` | Pet name request | |
| 5 | `Whiskers` | Species request | |
| 6 | `cat` | Breed request | |
| 7 | `skip` | Gender request | |
| 8 | `skip` | DOB request | |
| 9 | `skip` | Weight request | |
| 10 | `skip` | Neutered request | |
| 11 | `skip` | Completion message with dashboard link | |

**Verify after completion:**
- [ ] Dashboard shows: Whiskers, Cat, Breed: —, Gender: —, DOB: —, Weight: —, Neutered: No
- [ ] Cat-specific preventive items seeded (includes Feline Core instead of Core Vaccine)

---

## Test Flow 3: Consent Declined

**Goal:** Verify user who declines consent is soft-deleted.

| Step | You Send | Expected Response | Pass? |
|------|----------|-------------------|-------|
| 1 | `Hello` (from new number) | Welcome + consent request | |
| 2 | `no` | _"No problem. Your data won't be stored."_ | |

**Verify:**
- [ ] User record exists in DB with `is_deleted=true`
- [ ] Sending another message later restarts onboarding fresh

---

## Test Flow 4: Invalid Input Handling

**Goal:** Verify validation during onboarding.

| Step | You Send | Expected Response | Pass? |
|------|----------|-------------------|-------|
| During species step | `bird` | _"Please reply dog or cat."_ | |
| During species step | `dog` | Proceeds to breed | |
| During pincode step | `ABC` | _"Please enter a valid 6-digit Indian pincode, or type skip."_ | |
| During pincode step | `12345` | Same error (needs 6 digits) | |
| During DOB step | `tomorrow` | _"Invalid date format."_ | |
| During weight step | `-5` | Error message about valid weight | |
| During weight step | `1000` | Error message (max 999.99) | |

---

## Test Flow 5: Document Upload

**Goal:** Upload a medical document and verify extraction.

| Step | Action | Expected Response | Pass? |
|------|--------|-------------------|-------|
| 1 | Send a **photo** of a vaccination record (JPEG/PNG) | _"Document received for Buddy! Extracting health data..."_ | |
| 2 | Wait 10-30 seconds | Extraction result message with items found, OR conflict messages if dates differ | |
| 3 | Send a **PDF** blood test report | Same extraction flow | |

**Verify:**
- [ ] Document appears in dashboard "Uploaded Documents" section
- [ ] Extraction status shows "success" (or "failed" with error)
- [ ] If items were extracted, preventive records updated with dates
- [ ] Health score recalculated

**Error cases to test:**
| Action | Expected | Pass? |
|--------|----------|-------|
| Send a `.txt` file | Rejected — invalid MIME type | |
| Send a file > 10MB | Rejected — file too large | |
| Upload 11 files in one day | 11th rejected — daily limit exceeded | |

---

## Test Flow 6: Conflict Resolution

**Goal:** Trigger and resolve a data conflict.

**Setup:** Pet must have a preventive record with an existing date (e.g., Rabies Vaccine done on 2024-06-15).

| Step | Action | Expected Response | Pass? |
|------|--------|-------------------|-------|
| 1 | Upload a document that shows Rabies Vaccine on a **different date** (e.g., 2024-07-20) | Conflict message: _"Data Conflict for Buddy — Rabies Vaccine — Existing: 2024-06-15, New: 2024-07-20"_ | |
| 2 | Receive interactive buttons: "Use New Date" / "Keep Existing" | Two buttons appear | |
| 3a | Tap **"Use New Date"** | _"Updated to the new date."_ — Record changes to 2024-07-20 | |
| 3b | OR tap **"Keep Existing"** | _"Kept the existing date."_ — Record stays at 2024-06-15 | |

**Verify:**
- [ ] Dashboard reflects the chosen date
- [ ] Next due date recalculated if new date was used
- [ ] Conflict flag status = "resolved" in admin panel

**Auto-resolution test:**
- [ ] If no button is tapped for 5 days, conflict auto-resolves with KEEP_EXISTING
- [ ] No message sent to user on auto-resolve

---

## Test Flow 7: Reminder Response Buttons

**Goal:** Test all 4 reminder button responses.

**Setup:** Trigger a reminder manually via admin panel or wait for 8 AM IST cron.

| Button | Expected Result | Verify in Dashboard | Pass? |
|--------|----------------|---------------------|-------|
| **Done** | _"Marked as done! Next due: {date}"_ | `last_done_date` = today, `next_due_date` recalculated, status = up_to_date | |
| **Snooze 7 days** | _"Snoozed for 7 days. New due: {date}"_ | `next_due_date` pushed 7 days forward | |
| **Reschedule** | _"Please send the new date"_ → send `05/04/2025` | `next_due_date` = 2025-04-05 | |
| **Cancel** | _"Reminder cancelled."_ | Record status = cancelled, excluded from future reminders | |

---

## Test Flow 8: Add Second Pet

**Goal:** Add another pet after onboarding is complete.

| Step | You Send | Expected Response | Pass? |
|------|----------|-------------------|-------|
| 1 | `add pet` | _"What is your pet's name?"_ | |
| 2 | `Milo` | _"Is Milo a dog or a cat?"_ | |
| 3 | `cat` | Breed request | |
| 4-8 | Complete remaining fields | Completion message with NEW dashboard link for Milo | |

**Verify:**
- [ ] New dashboard link works and shows Milo's data
- [ ] Original Buddy dashboard still works
- [ ] Cat-specific preventive items seeded for Milo
- [ ] Requesting "dashboard" shows links for BOTH pets

**Max pets test:**
- [ ] After adding 5 pets, sending "add pet" returns: _"You already have 5 pets registered. Maximum is 5."_

---

## Test Flow 9: Dashboard Link Request

**Goal:** Request dashboard links via WhatsApp.

| Step | You Send | Expected Response | Pass? |
|------|----------|-------------------|-------|
| 1 | `dashboard` | Dashboard link(s) for all pets | |
| 2 | `link` | Same as above | |
| 3 | `my dashboard` | Same as above | |

**Verify:**
- [ ] Each pet gets its own unique link
- [ ] Expired tokens are regenerated automatically
- [ ] Links work in mobile browser

---

## Test Flow 10: Health Query (AI-Powered)

**Goal:** Ask questions about your pet's health.

| You Send | Expected Behavior | Pass? |
|----------|-------------------|-------|
| `What vaccines does Buddy need?` | AI response grounded in Buddy's preventive records | |
| `Is Buddy overdue for anything?` | Lists overdue items from records | |
| `When is the next checkup?` | Shows upcoming due dates | |
| `What is deworming?` | General info contextualized to your pet | |

**Verify:**
- [ ] Responses reference actual pet data (not generic)
- [ ] No hallucinated items (only from preventive_master)
- [ ] Response arrives within 5-10 seconds

---

## Test Flow 11: User Dashboard (Browser)

**Goal:** Test all dashboard features in browser.

**URL:** `https://pet-circle-chi.vercel.app/dashboard/{token}`

### 11a: Pet Profile Card
| Action | Expected | Pass? |
|--------|----------|-------|
| View profile | Pet name, species, breed, gender, DOB, weight, neutered displayed | |
| Click "Edit" on weight | Input field appears with Save/Cancel | |
| Enter `30.0` and click Save | Weight updates, page refreshes | |
| Enter `0` and click Save | Error: _"Enter a valid weight (0.01 - 999.99 kg)"_ | |
| Click Cancel | Edit mode closes, original weight shown | |

### 11b: Health Score Ring
| Check | Expected | Pass? |
|-------|----------|-------|
| Score displays | Number 0-100 in circular ring | |
| Color matches score | Green (>=80), Yellow (50-79), Red (<50) | |
| Mandatory/Recommended counts | Shows "Mandatory: X/Y" and "Recommended: X/Y" | |

### 11c: Preventive Records Table
| Action | Expected | Pass? |
|--------|----------|-------|
| View table | All preventive items listed with columns: Item, Category, Last Done, Next Due, Status, Recurrence, Action | |
| Status badges | Green (up_to_date), Yellow (upcoming), Red (overdue), Gray (cancelled) | |
| Click "Update date" | Date input appears with DD/MM/YYYY placeholder | |
| Enter `01/03/2025` and Save | Date updates, next due recalculates, status recalculates | |
| Cancelled item | No "Update date" button shown | |

### 11d: Reminders & Documents
| Check | Expected | Pass? |
|-------|----------|-------|
| Reminders table | Shows active reminders with status dots (blue=sent, yellow=pending) | |
| Documents table | Shows uploaded docs with MIME icon and extraction status | |
| Empty state | _"No active reminders."_ / _"No documents uploaded yet."_ | |

### 11e: Security
| Action | Expected | Pass? |
|--------|----------|-------|
| Visit `/dashboard/invalidtoken123` | Error: _"Unable to load dashboard"_ | |
| Visit dashboard after admin revokes token | Error: _"Unable to load dashboard"_ | |

---

## Test Flow 12: Admin Dashboard (Browser)

**URL:** `https://pet-circle-chi.vercel.app/admin`

### 12a: Authentication
| Action | Expected | Pass? |
|--------|----------|-------|
| Visit `/admin` | Login form with "Admin Key" input | |
| Enter wrong key, click Sign In | _"Invalid admin key"_ error | |
| Enter correct `ADMIN_SECRET_KEY` | Admin dashboard loads with 5 tabs | |
| Click Logout | Returns to login form | |

### 12b: Users Tab
| Check | Expected | Pass? |
|-------|----------|-------|
| Users table loads | All users listed with Name, Mobile (masked), Pincode, Consent, State, Status, Created | |
| Mobile number masked | Shows `+91XXXX5679` format (not full number) | |
| Active user | Green "Active" badge | |
| Click Delete | Confirmation dialog → user marked as Deleted (red badge) | |
| Deleted user | No Delete button shown | |

### 12c: Pets Tab
| Check/Action | Expected | Pass? |
|--------------|----------|-------|
| Pets table loads | All pets with Name, Species, Breed, Gender, DOB, Weight, Neutered, Status | |
| Click "Revoke token" | Confirmation → token revoked, dashboard link stops working | |
| Click "Trigger reminder" | Alert: _"Reminder triggered"_ | |

### 12d: Reminders Tab
| Check | Expected | Pass? |
|-------|----------|-------|
| Table loads | Pet name, Item, Due Date, Record Status, Reminder Status, Sent At | |
| Status badges | Color-coded: pending (yellow), sent (blue), completed (green), snoozed (purple) | |

### 12e: Documents Tab
| Check | Expected | Pass? |
|-------|----------|-------|
| Table loads | Pet name, MIME Type, Extraction Status, File Path, Created | |
| Extraction badges | success (green), pending (yellow), failed (red) | |

### 12f: Messages Tab
| Check/Action | Expected | Pass? |
|--------------|----------|-------|
| Table loads | Direction, Mobile (masked), Type, Payload, Time | |
| Click "Incoming" filter | Only incoming messages shown | |
| Click "Outgoing" filter | Only outgoing messages shown | |
| Click "All" | All messages shown | |

---

## Test Flow 13: Reminder Engine (Cron)

**Goal:** Verify the daily reminder job works.

**Manual trigger:** `POST https://pet-circle.onrender.com/internal/run-reminder-engine` with header `X-ADMIN-KEY: {ADMIN_SECRET_KEY}`

Or via admin panel: Pets tab → "Trigger reminder" button on specific pet.

| Check | Expected | Pass? |
|-------|----------|-------|
| Engine runs without error | Returns `{"status":"triggered","results":{...}}` | |
| Upcoming items get reminders | WhatsApp template message sent for items due within 7 days | |
| Overdue items get reminders | WhatsApp overdue template sent for past-due items | |
| Already-sent reminders skipped | No duplicate messages for same item + due date | |
| Reminder appears in dashboard | Reminders section shows new entries | |
| Message logged | Messages tab in admin shows outgoing template | |

---

## Test Flow 14: Edge Cases

| Scenario | Action | Expected | Pass? |
|----------|--------|----------|-------|
| **Expired token** | Wait 30 days, visit dashboard | Error page, request new link via "dashboard" on WhatsApp | |
| **Revoked token** | Admin revokes, user visits | Error page | |
| **Rate limit** | Send 21+ messages in 1 minute | Messages silently dropped after limit | |
| **Concurrent updates** | Two browser tabs update same record | Last write wins, both refresh correctly | |
| **Empty pet** | Onboard with all skips | Dashboard shows dashes for all optional fields | |
| **Special characters** | Pet name: `Max Jr. (2nd)` | Name stored and displayed correctly | |
| **Long name** | 100-char pet name | Accepted (max limit) | |
| **101-char name** | 101-char pet name | Rejected with error | |

---

## Test Flow 15: API Health Checks

Test these endpoints directly (use browser or curl):

| Endpoint | Method | Expected | Pass? |
|----------|--------|----------|-------|
| `/health` | GET | `{"status":"healthy","timezone":"Asia/Kolkata"}` | |
| `/webhook/whatsapp?hub.mode=subscribe&hub.verify_token={TOKEN}&hub.challenge=test123` | GET | `test123` (webhook verification) | |
| `/admin/verify-key` with wrong key | POST | `403 Forbidden` | |
| `/dashboard/nonexistent` | GET | `404` or error JSON | |

---

## Test Results Log

| Date | Tester | Flow # | Result | Notes |
|------|--------|--------|--------|-------|
| | | | | |
| | | | | |
| | | | | |

---

## Quick Reference: WhatsApp Keywords

| Keyword | Action |
|---------|--------|
| `yes` / `y` / `agree` | Accept consent |
| `no` | Decline consent |
| `skip` | Skip optional field |
| `dog` / `cat` | Species selection |
| `male` / `female` | Gender selection |
| `add pet` / `new pet` | Start adding another pet |
| `dashboard` / `link` | Request dashboard link(s) |
| Any other text | Routed to AI query engine |

## Quick Reference: Date Formats Accepted

| Format | Example |
|--------|---------|
| DD/MM/YYYY | 15/03/2024 |
| DD-MM-YYYY | 15-03-2024 |
| DD Month YYYY | 15 March 2024 |
| YYYY-MM-DD | 2024-03-15 |

## Quick Reference: Button Payloads

| Button | Payload ID | Action |
|--------|-----------|--------|
| Done | `REMINDER_DONE` | Mark item done today |
| Snooze 7 days | `REMINDER_SNOOZE_7` | Push due date 7 days |
| Reschedule | `REMINDER_RESCHEDULE` | Enter new date |
| Cancel | `REMINDER_CANCEL` | Cancel this reminder |
| Use New Date | `CONFLICT_USE_NEW` | Accept extracted date |
| Keep Existing | `CONFLICT_KEEP_EXISTING` | Keep current date |
