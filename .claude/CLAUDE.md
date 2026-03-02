# Agent Instructions — PetCircle Phase 1: WhatsApp Preventive Health System

You're working inside the **WAT framework** (Workflows, Agents, Tools). This architecture separates concerns so that probabilistic AI handles reasoning while deterministic code handles execution. That separation ensures reliability at scale.

---

## The WAT Architecture

**Layer 1: Workflows (The Instructions)**
- Markdown SOPs stored in `workflows/`
- Each workflow defines objectives, required inputs, which tools to use, expected outputs, and edge case handling
- Written in plain language for developers
- Examples:
  - `workflows/onboard_pet_parent.md`
  - `workflows/record_preventive_event.md`
  - `workflows/handle_conflict.md`
  - `workflows/send_reminder.md`

**Layer 2: Agents (The Decision-Maker)**
- Responsible for orchestrating workflows across the WhatsApp automation pipeline
- Reads workflows, identifies required inputs, calls tools in correct order, handles failures
- Example: When a new record is uploaded, the agent validates it, checks conflicts, updates DB, triggers GPT extraction, and schedules reminders

**Layer 3: Tools (The Execution)**
- Deterministic scripts in `tools/` handle the actual work
- Examples:
  - WhatsApp Cloud API calls
  - OpenAI GPT extraction
  - Database CRUD operations
  - Reminder scheduling
- Credentials stored in `.env` only — never hardcoded

---

## Core Production Principles

**1. Never process logic inside the webhook**
- Webhook does only: signature verification, payload validation, enqueue
- Returns `200 OK` immediately

**2. Queue all AI or external API calls**
- GPT extraction, third-party lookups, and reminders belong in workers
- Enables retries, rate-limiting, and isolation

**3. DB is source of truth**
- No in-memory state
- Every transition must be written to PostgreSQL

**4. Separate environments**
- Local: ngrok + local Postgres + Redis
- Production: managed services
- Never share credentials or URLs between environments

**5. Security is structural**
- Signature verification first
- Passwords bcrypt-hashed
- Tokens in HttpOnly cookies
- Admin endpoints RBAC-protected
- Rate limiting enforced

---

## How to Operate

**1. Use existing tools first**
- Check `tools/` before creating new scripts

**2. Follow message processing flow**

```
Inbound Message (Meta Webhook)
  → Verify signature (tools/verify_webhook_signature.py)
  → Validate payload (tools/validate_message_payload.py)
  → Enqueue job (tools/enqueue_message_job.py)
  → Return 200

Worker picks up job:
  → Load conversation state (tools/get_conversation_state.py)
  → Run business logic (conflict detection, reminder scheduling, GPT extraction)
  → Update DB (tools/update_conversation_state.py)
  → Send WhatsApp reply/template (tools/send_whatsapp_message.py)
  → Log activity (tools/log_message.py)
```

**3. Learn from failures**
- Trace the error
- Identify if failure is tool, workflow, or infrastructure
- Fix root cause
- Update workflow to prevent recurrence

**4. Keep workflows current**
- Update SOPs when better approaches or constraints are discovered
- Avoid overwriting workflows without approval

---

## System-Specific Constraints (PetCircle Phase 1)

- **Country & Timezone:** India, Asia/Kolkata
- **Max pets per user:** 5
- **File upload:** Max 10MB, MIME types `jpeg/png/pdf`, max 10 per day per pet
- **Dashboard token:** 128-bit random, unique, revocable, soft delete only
- **Conflict expiry:** 5 days, auto-resolve KEEP_EXISTING, log action
- **Preventive master:** Frozen, always read from DB, no fallback
- **WhatsApp templates:** All loaded from environment, no hardcoding
- **OpenAI GPT:** Extraction: `gpt-4.1`, Query: `gpt-4.1-mini`, strict JSON, retry policy applied
- **Storage:** Private S3 bucket `petcircle-documents`, path `{user_id}/{pet_id}/{filename}`, no public URLs
- **Admin security:** Header `X-ADMIN-KEY` validated against `ADMIN_SECRET_KEY`
- **Button payload IDs:** No hardcoding, e.g., `REMINDER_DONE`, `CONFLICT_USE_NEW`
- **Date rules:** Accepted formats `DD/MM/YYYY`, `DD-MM-YYYY`, `12 March 2024`, ISO; stored `YYYY-MM-DD`
- **Rate limiting:** Max 20 messages/min per number, rolling window enforced
- **DB constraints:** Reminder deduplication and preventive record uniqueness enforced; explicit transactions; idempotency
- **WhatsApp webhook:** Validate `X-Hub-Signature-256`; log all messages; 1 retry only
- **Conflict engine:** Triggered if extracted date differs; requires explicit user decision; safe expiry
- **Reminder engine:** Daily 8 AM IST, stateless, no duplicates, retry once, logging mandatory
- **Dashboard rules:** Token validated, recalc `next_due_date`, update status, no internal IDs exposed
- **Logging rules:** All WhatsApp and OpenAI messages logged; must not block flow
- **Security rules:** No hardcoding, all env variables mandatory, no silent overwrites, all limits constants
- **Failure behavior:** Never crash due to GPT/WhatsApp/logging; crash for missing env or DB constraint violation
- **Coding discipline:** Docstrings for all classes/functions, comment business rules, wrap GPT calls, log WhatsApp messages, modular, readable

---

## PetCircle – Phase 1 Final Software Architecture

### 1️⃣ Core Stack

**Backend API**
- Python + FastAPI
- Handles:
  - WhatsApp webhook handling
  - Business logic processing
  - AI extraction orchestration
  - Reminder engine execution
  - Admin APIs & tokenized dashboard access

**Messaging Integration**
- WhatsApp Cloud API
- Receives messages, sends replies/templates, dashboard links

**AI Processing**
- OpenAI GPT API
- Extracts structured health summaries from uploaded documents
- Strictly grounded in DB data

**Database & File Storage**
- Supabase (PostgreSQL + storage buckets)
- Stores: structured data, media, consent logs, reminder states

**Frontend (Dashboard)**
- Next.js + Tailwind CSS
- Displays pet health dashboard, records, reminders, admin panel
- Token-based secure access (no login for Phase 1)

**Hosting & Deployment**
- Render
- Backend API hosting, cron jobs for reminders, automatic Git deployments

### 2️⃣ System Architecture Flow

```
User (WhatsApp)
        ↓
WhatsApp Cloud API
        ↓
FastAPI Webhook Endpoint
        ↓
Message Processing Layer
        ↓
Business Logic Layer
        ↓
Supabase (DB + Storage)
        ↓
OpenAI GPT (Extraction)
        ↓
Reminder Engine (Render Cron)
        ↓
WhatsApp Template Messages
        ↓
Next.js Dashboard (Token-based Access)
```

### 3️⃣ Architectural Layers (Strict Separation)

**Webhook Layer**
- Handles incoming WhatsApp events, media download triggers, message parsing
- No business logic

**Service Layer**
- Handles pet creation, record updates, preventive tracking, reminder calculations, AI extraction
- Core logic engine

**Data Layer**
- Supabase PostgreSQL tables: users, pets, preventive_records, reminders, documents, message_logs, consent_logs, dashboard_tokens
- Strict relational structure

**Reminder Engine**
- Daily scheduled job on Render
- Queries due items, checks completion, sends template messages, updates reminder state
- Stateless execution

**Dashboard Layer**
- Next.js fetches data via backend API
- Token validation middleware
- Read-only shared links, admin-only routes

### 4️⃣ Security Model

- Mobile number as unique identifier
- Consent logged with timestamp
- Dashboard access via secure random token
- Media files in private Supabase bucket; no public URLs

### 5️⃣ What This Architecture Avoids (Intentionally)

- No microservices, Redis, Kafka, Docker complexity
- No separate auth provider, payment integration, or background job queue
- Clean monolithic backend with clear layers

### 6️⃣ Final Architecture Summary

| Component | Technology |
|-----------|------------|
| Backend | Python + FastAPI |
| Messaging | WhatsApp Cloud API |
| AI | OpenAI GPT |
| Database & Storage | Supabase |
| Frontend | Next.js |
| Hosting | Render |
| Reminder Engine | Render Cron |

---

## Bottom Line

You are the bridge between workflows (instructions) and tools (execution). Orchestrate PetCircle Phase 1 with precision:
- Enforce constraints
- Never skip steps
- Handle failures safely
- Keep documentation current
- Build as if serving tens of thousands of users

