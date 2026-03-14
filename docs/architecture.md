# PetCircle — Architecture Overview

## System Purpose

PetCircle is a WhatsApp-based preventive pet health system for India. Pet parents interact via WhatsApp to track vaccinations, deworming, lab tests, and other preventive care items. The system sends reminders, extracts data from uploaded documents using AI, and provides a web dashboard for viewing health records.

## Architecture Pattern: WAT Framework

The system uses the **WAT** (Workflows, Agents, Tools) pattern:

- **Workflows** (`workflows/`): Markdown SOPs defining each business process step-by-step
- **Agents**: The orchestration layer (FastAPI routers + message router) that reads workflows and calls tools
- **Tools** (`backend/app/services/`): Deterministic Python modules that execute specific operations

## System Flow

```
User (WhatsApp)
    |
    v
WhatsApp Cloud API
    |
    v
FastAPI Webhook (/webhook/whatsapp)
    |
    v
Message Router (app/services/message_router.py)
    |
    +---> Onboarding Service
    +---> Document Upload + GPT Extraction
    +---> Conflict Engine
    +---> Reminder Response Handler
    +---> Order Service (order placement + admin fulfillment check)
    +---> Query Engine
    |
    v
Supabase (PostgreSQL + Storage)
    |
    v
Reminder Engine (daily cron at 8 AM IST)
    |
    v
WhatsApp Template Messages
    |
    v
Next.js Dashboard (token-based access)
```

## Component Map

| Component | Technology | Location |
|-----------|------------|----------|
| Backend API | Python 3.11 + FastAPI | `backend/` |
| Messaging | WhatsApp Cloud API | `backend/app/services/whatsapp_sender.py` |
| AI Extraction | OpenAI GPT (gpt-4.1) | `backend/app/services/gpt_extraction.py` |
| AI Query | OpenAI GPT (gpt-4.1-mini) | `backend/app/services/query_engine.py` |
| Database | Supabase (PostgreSQL) | `backend/app/database.py`, `backend/app/models/` |
| File Storage | Supabase Storage (private) | `backend/app/services/document_upload.py` |
| Frontend | Next.js 14 + Tailwind | `frontend/` |
| Backend Hosting | Render | `render.yaml` |
| Frontend Hosting | Vercel | `frontend/` |
| Cron | GitHub Actions | `.github/workflows/reminder-cron.yml` |

## Key Design Decisions

1. **Monolithic backend**: No microservices. All logic in one FastAPI app with clear layer separation.
2. **No background queue**: Phase 1 processes inline. Queue can be added later if needed.
3. **Token-based dashboard**: No login system. Secure random tokens shared via WhatsApp.
4. **Supabase for everything**: PostgreSQL + Storage in one managed service.
5. **Environment-aware config**: `APP_ENV` controls which env file is loaded (development/test/production).

## Order Notification Flow

- When a user confirms an order, the backend sends a WhatsApp template notification to `ORDER_NOTIFICATION_PHONE` (if configured).
- The template name is loaded from `WHATSAPP_TEMPLATE_ORDER_FULFILLMENT_CHECK`.
- If `ORDER_NOTIFICATION_PHONE` is not configured, the order is still saved and user confirmation is unaffected.

## Security Model

- Mobile number as unique user identifier
- WhatsApp webhook signature verification (`X-Hub-Signature-256`)
- Admin endpoints require `X-ADMIN-KEY` header
- Dashboard access via 128-bit random token
- Media files in private Supabase bucket (no public URLs)
- All secrets loaded from environment variables (never hardcoded)
