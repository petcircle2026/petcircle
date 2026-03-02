
# 🧱 PETCIRCLE BACKEND — DETERMINISTIC BUILD SPECIFICATION

# MODULE 1 — PROJECT SKELETON

Create:

```
petcircle-backend/
│
├── app/
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── core/
│   ├── models/
│   ├── schemas/~
│   ├── services/
│   ├── routers/
│   └── utils/
│
├── requirements.txt
├── .env.example
├── CLAUDE.md
└── README.md
```

Tech stack:

* Python 3.11
* FastAPI
* SQLAlchemy
* Supabase PostgreSQL
* httpx
* openai

requirements.txt:

```
fastapi
uvicorn
sqlalchemy
psycopg2-binary
supabase
python-dotenv
httpx
pydantic
openai
pytz
```

No business logic yet.

---

# MODULE 2 — DATABASE SCHEMA (LOCKED)

Use the exact SQL provided earlier in this conversation.

Do NOT modify.
Do NOT add columns.
Do NOT infer fields.

All constraints exactly as frozen.

Create SQLAlchemy models that mirror tables 1:1.

Every model must:

* Include docstring describing purpose
* Include comment explaining unique constraints
* Include comment explaining foreign keys

Soft delete fields must not cascade physical delete.

---

# MODULE 3 — CONFIG + ENVIRONMENT

Create `config.py` using Pydantic BaseSettings.

Required environment variables:

```
OPENAI_API_KEY=
SUPABASE_URL=
SUPABASE_KEY=
SUPABASE_SERVICE_ROLE_KEY=
WHATSAPP_TOKEN=
WHATSAPP_VERIFY_TOKEN=
WHATSAPP_PHONE_NUMBER_ID=
SUPABASE_BUCKET_NAME=
WHATSAPP_TEMPLATE_REMINDER=
WHATSAPP_TEMPLATE_OVERDUE=
WHATSAPP_TEMPLATE_NUDGE=
WHATSAPP_TEMPLATE_CONFLICT=
WHATSAPP_TEMPLATE_ONBOARDING_COMPLETE=
ADMIN_SECRET_KEY=
```

Startup behavior:

* If any missing → raise RuntimeError
* Print clear error which variable missing
* Fail application

Timezone constant must be defined here:
Asia/Kolkata

---

# MODULE 4 — WHATSAPP WEBHOOK LAYER

Route: `/webhook/whatsapp`

Must support:

GET:

* Verify token match
* Return challenge

POST:

* Parse nested payload safely
* Detect:

  * text
  * image
  * document
  * button
* Log ALL incoming payloads to message_logs
* Pass structured object to service layer

No business logic here.

Robust nested dictionary extraction required.

---

# MODULE 5 — ONBOARDING STATE MACHINE

States:

* ask_full_name
* ask_pincode
* ask_pet_name
* ask_species
* ask_breed
* ask_gender
* ask_dob
* ask_weight
* ask_neutered
* complete

Rules:

* No skipping
* No branching
* Store temporary state in DB (NOT memory)
* On complete:

  * Create user
  * Create pet
  * Generate 128-bit random dashboard token
  * Send petcircle_onboarding_complete_v1 template

Limit 5 pets per user enforced in service layer.

All state transitions documented with comments.

---

# MODULE 6 — PREVENTIVE MASTER SEEDER

Insert exact frozen table:

Rabies Vaccine
Core Vaccine
Feline Core
Deworming
Tick/Flea
Annual Checkup
Preventive Blood Test
Dental Check

Rules:

* Insert only if table empty
* Enforce unique(item_name, species)
* Never reference recurrence outside DB

---

# MODULE 7 — FILE UPLOAD + GPT EXTRACTION

Steps:

1. Validate file size ≤ 10MB
2. Validate MIME allowed
3. Upload to Supabase private bucket:
   `{user_id}/{pet_id}/{filename}`
4. Insert document record
5. Call OpenAI extraction model

Extraction model config:

* Model: gpt-4.1
* Temperature: 0
* Max tokens: 1500
* JSON only

Retry 2 times.

If failure:

* extraction_status = failed
* Notify user
* Do not crash

If success:

* Validate JSON keys strictly
* Normalize date format
* Pass to preventive service

No medical advice allowed.

---

# MODULE 8 — CONFLICT DETECTION ENGINE

When new preventive date extracted:

If existing latest date exists and differs:

* Insert conflict_flags row
* status = pending
* Send petcircle_conflict_v1

No overwrite allowed.

Conflict expiry:

* 5 days
* Auto resolve KEEP_EXISTING
* status = auto_resolved
* Log action

No partial merge allowed.

---

# MODULE 9 — PREVENTIVE CALCULATOR

When last_done_date saved:

Fetch recurrence_days from preventive_master.

Compute:

```
next_due_date = last_done_date + recurrence_days
```

Status logic:

* today > next_due → overdue
* today + reminder_before_days >= next_due → upcoming
* else → up_to_date

Timezone strictly Asia/Kolkata.

No hidden logic.

---

# MODULE 10 — REMINDER ENGINE

Route: `/internal/run-reminder-engine`

Cron: 8 AM IST daily.

Steps:

1. Find preventive_records needing reminder
2. Check UNIQUE(preventive_record_id, next_due_date)
3. Insert reminder if not exists
4. Send template
5. Update reminder.status = sent

Retry WhatsApp once.

Stateless execution.

---

# MODULE 11 — REMINDER RESPONSE STATE MACHINE

Payload IDs (constants):

REMINDER_DONE
REMINDER_SNOOZE_7
REMINDER_RESCHEDULE
REMINDER_CANCEL

Logic:

If DONE:

* Update last_done_date = today
* Recalculate
* reminder.status = completed

If SNOOZE:

* next_due_date += 7
* reminder.status = snoozed

If RESCHEDULE:

* Ask date
* Validate
* Update next_due_date

If CANCEL:

* preventive_record.status = cancelled

All logic commented thoroughly.

---

# MODULE 12 — HEALTH SCORE ENGINE

Compute:

```
Score = (
 (E_done / E_total) * 0.9 +
 (C_done / C_total) * 0.1
) * 100
```

Round to nearest integer.

No partial logic.

---

# MODULE 13 — DASHBOARD TOKEN API

Route: `GET /dashboard/{token}`

Validate:

* token exists
* not revoked

Return:

* pet profile
* preventive summary
* reminders
* documents
* health score

Editable endpoints:

* update weight
* update preventive dates

Must:

* Recalculate after update
* Invalidate pending reminder if date changes

No bucket hardcoding.

---

# MODULE 14 — STRICT QUERY ENGINE

Model: gpt-4.1-mini

System prompt:

"You may ONLY answer using provided data. If information is not available, say: I don’t have that information in your pet’s records."

No medical advice.
No external knowledge.

Retry policy applied.

---

# MODULE 15 — ADMIN PANEL APIs

Routes:

GET /admin/users
GET /admin/pets
GET /admin/reminders
GET /admin/documents
PATCH /admin/revoke-token/{pet_id}
PATCH /admin/soft-delete-user/{user_id}
POST /admin/trigger-reminder/{pet_id}

Validate header:

X-ADMIN-KEY

Compare with ADMIN_SECRET_KEY.

Reject if mismatch.

No RBAC.

---

# MODULE 16 — CONSTANTS

Create central constants file.

Include:

* MAX_PETS_PER_USER
* MAX_UPLOAD_MB
* ALLOWED_MIME_TYPES
* SYSTEM_TIMEZONE
* CONFLICT_EXPIRY_DAYS

No magic numbers anywhere else.

---

# MODULE 17 — RETRY UTILITIES

Implement:

retry_openai_call()
retry_whatsapp_call()

OpenAI:

* 1s backoff
* 2s backoff
* fail on 3rd

WhatsApp:

* retry once
* log failure
* continue

Database:
no retry

---

# MODULE 18 — DATE UTILITY

Accept formats:

DD/MM/YYYY
DD-MM-YYYY
12 March 2024
ISO

Convert to YYYY-MM-DD.

Use pytz Asia/Kolkata.

Raise clear validation errors.

---

# MODULE 19 — CONFLICT EXPIRY CRON

Extend reminder cron:

* Check conflict_flags older than 5 days
* Auto resolve
* Log system action
* No user notification

---

# CLAUDE CODING ENFORCEMENT

Claude must:

* Add docstrings to every class and function
* Comment all business rules
* Comment why constraints exist
* Comment idempotency protection
* Comment retry reasoning
* Comment timezone reasoning
* Comment deduplication reasoning
* Comment conflict logic reasoning

Code must be production readable.

No short ambiguous code.

---

# SYSTEM STATUS

Now:

* All schema frozen
* All APIs defined
* All retries defined
* All templates defined
* All constraints defined
* All expiry logic defined
* All uniqueness rules defined
* All MIME defined
* All deduplication defined
* All scoring defined
* All auth defined
* All tokens defined
* No drift possible


