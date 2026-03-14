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
  - `workflows/process_document_upload.md`
  - `workflows/handle_reminder_response.md`
  - `workflows/resolve_conflict_expiry.md`
  - `workflows/BIRTHDAY_REMINDER_GUIDE.md`

**Layer 2: Agents (The Decision-Maker)**
- Responsible for orchestrating workflows across the WhatsApp automation pipeline
- Reads workflows, identifies required inputs, calls services in correct order, handles failures
- Example: When a new record is uploaded, the agent validates it, checks conflicts, updates DB, triggers GPT extraction, and schedules reminders

**Layer 3: Tools (The Execution)**
- Deterministic service modules in `backend/app/services/` handle the actual work
- Key services:
  - `whatsapp_sender.py` — WhatsApp Cloud API calls
  - `gpt_extraction.py` — OpenAI GPT extraction
  - `message_router.py` — Routes incoming messages to appropriate handlers
  - `onboarding.py` — Onboarding state machine
  - `reminder_engine.py` — Reminder scheduling and sending
  - `conflict_engine.py` — Conflict detection and resolution
  - `birthday_service.py` — Birthday reminder logic
  - `order_service.py` — Product order management
  - `recommendation_service.py` — AI-powered order recommendations
- Credentials stored in `.env` only — never hardcoded

---

## Core Production Principles

**1. Never process logic inside the webhook**
- Webhook does only: signature verification, payload validation, dispatch to background task
- Returns `200 OK` immediately

**2. Offload all AI or external API calls to background tasks**
- GPT extraction, third-party lookups, and reminders run in `asyncio.create_task()` background tasks
- Enables non-blocking processing; webhook returns immediately

**3. DB is source of truth**
- No in-memory state
- Every transition must be written to PostgreSQL

**4. Separate environments**
- Development: ngrok + Supabase dev project
- Production: Render + Supabase production project
- Never share credentials or URLs between environments

**5. Security is structural**
- Signature verification first
- Passwords bcrypt-hashed
- Tokens in HttpOnly cookies
- Admin endpoints RBAC-protected
- Rate limiting enforced

---

## How to Operate

**1. Use existing services first**
- Check `backend/app/services/` before creating new modules

**2. Follow message processing flow**

```
Inbound Message (Meta Webhook)
  → Verify signature (app/core/security.py: verify_webhook_signature)
  → Parse & validate payload (app/routers/webhook.py: _extract_message_data)
  → Dispatch background task via asyncio.create_task()
  → Return 200

Background task runs:
  → Route message (app/services/message_router.py: route_message)
  → Execute business logic (onboarding, document upload, conflict, reminder response, query)
  → Update DB via service layer (direct SQLAlchemy queries)
  → Send WhatsApp reply/template (app/services/whatsapp_sender.py)
  → Log activity (message_logs table)
```

**3. Learn from failures**
- Trace the error
- Identify if failure is service, workflow, or infrastructure
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
- Backend: Render (API hosting, automatic Git deployments)
- Frontend: Vercel (Next.js hosting, automatic Git deployments)
- Cron: GitHub Actions (daily reminder engine at 8 AM IST)

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
Reminder Engine (GitHub Actions Cron)
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
- Supabase PostgreSQL tables: users, pets, preventive_records, preventive_master, reminders, documents, message_logs, dashboard_tokens, conflict_flags, orders, order_recommendations, diagnostic_test_results, pet_preferences, shown_fun_facts
- Strict relational structure

**Reminder Engine**
- Daily scheduled job via GitHub Actions
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
- No separate auth provider or payment integration
- Background processing via asyncio.create_task() (no external job queue)
- Clean monolithic backend with clear layers

### 6️⃣ Final Architecture Summary

| Component | Technology |
|-----------|------------|
| Backend | Python + FastAPI |
| Messaging | WhatsApp Cloud API |
| AI | OpenAI GPT |
| Database & Storage | Supabase |
| Frontend | Next.js |
| Backend Hosting | Render |
| Frontend Hosting | Vercel |
| Reminder Engine | GitHub Actions Cron |

---

## Bottom Line

You are the bridge between workflows (instructions) and services (execution). Orchestrate PetCircle with precision:
- Enforce constraints
- Never skip steps
- Handle failures safely
- Keep documentation current
- Build as if serving tens of thousands of users

