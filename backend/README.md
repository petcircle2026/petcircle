# PetCircle Backend — Phase 1

WhatsApp-based preventive pet health system built with FastAPI.

## Setup

```bash
# Create virtual environment
python -m venv venv

# Activate (Windows)
venv\Scripts\activate
# Activate (Linux/Mac)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Environment Variables

Copy `.env.example` to `.env` and fill in all values:

```bash
cp .env.example .env
```

All variables are required. The app will refuse to start if any are missing.

## Database

Tables are managed in Supabase (PostgreSQL). Run the SQL schema in your Supabase dashboard before starting the server. Then seed the preventive master table:

```bash
python -c "from app.database import SessionLocal; from app.services.preventive_seeder import seed_preventive_master; db = SessionLocal(); seed_preventive_master(db); db.close()"
```

## Running

```bash
# Development
uvicorn app.main:app --reload --port 8000

# Production (hosted on Render)
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

## API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | None | Health check |
| GET | `/webhook/whatsapp` | Query params | Meta webhook verification |
| POST | `/webhook/whatsapp` | X-Hub-Signature-256 | Incoming WhatsApp messages |
| GET | `/admin/users` | X-ADMIN-KEY | List all users |
| GET | `/admin/pets` | X-ADMIN-KEY | List all pets |
| GET | `/admin/reminders` | X-ADMIN-KEY | List all reminders |
| GET | `/admin/documents` | X-ADMIN-KEY | List all documents |
| PATCH | `/admin/revoke-token/{pet_id}` | X-ADMIN-KEY | Revoke dashboard token |
| PATCH | `/admin/soft-delete-user/{user_id}` | X-ADMIN-KEY | Soft delete user |
| POST | `/admin/trigger-reminder/{pet_id}` | X-ADMIN-KEY | Manual reminder trigger |
| POST | `/internal/run-reminder-engine` | X-ADMIN-KEY | Daily cron job |
| GET | `/dashboard/{token}` | Token in URL | Pet health dashboard |
| PATCH | `/dashboard/{token}/weight` | Token in URL | Update pet weight |
| PATCH | `/dashboard/{token}/preventive` | Token in URL | Update preventive date |

## Architecture

```
WhatsApp Cloud API → FastAPI Webhook → Message Router → Service Layer → Supabase
                                                       → OpenAI GPT (extraction)
                                                       → Reminder Engine (cron)
                                                       → Dashboard API (Next.js)
```

## Cron Jobs (GitHub Actions)

Daily at 8 AM IST:
```
POST /internal/run-reminder-engine
Header: X-ADMIN-KEY: <your-admin-key>
```
