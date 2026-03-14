# PetCircle — Environment Setup Guide

## Environment Strategy

PetCircle uses `APP_ENV` to select the configuration file:

| Environment | `APP_ENV` | Env File | Purpose |
|-------------|-----------|----------|---------|
| Development | `development` | `backend/envs/.env.development` | Local dev with real or test APIs |
| Test | `test` | `backend/envs/.env.test` | Automated tests with mock values |
| Production | `production` | *(none — hosting provider injects vars)* | Live system |

## Development Setup

### Prerequisites

- Python 3.11+
- Node.js 18+
- PostgreSQL (local or Supabase dev project)

### Backend

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt -r requirements-dev.txt

# Configure environment
cp envs/.env.example envs/.env.development
# Edit envs/.env.development with your credentials

# Seed preventive master data
python scripts/seed_preventive_master.py

# Run
APP_ENV=development uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend

npm install

# Configure environment
cp .env.example .env.local
# Edit .env.local — set NEXT_PUBLIC_API_URL=http://localhost:8000

npm run dev
```

### WhatsApp Webhook (Local)

For local development, use ngrok to expose your webhook:

```bash
ngrok http 8000
# Set the ngrok URL as your webhook URL in Meta Developer Portal
```

## Test Setup

Tests use mock values — no real API calls.

```bash
cd backend
APP_ENV=test pytest tests/ -v
```

The `tests/conftest.py` sets `APP_ENV=test` automatically, so you can also just run:

```bash
cd backend
pytest tests/ -v
```

## Production Setup

Production uses a split hosting model:

### Backend (Render)

1. Connect your GitHub repo to Render
2. Use `render.yaml` as the blueprint
3. Set all environment variables in the Render dashboard (see `backend/envs/.env.production.example` for the list)
4. Render auto-deploys backend on push to `main`

### Frontend (Vercel)

1. Connect your GitHub repo to Vercel
2. Set root directory to `frontend/`
3. Set `NEXT_PUBLIC_API_URL` to your production backend URL
4. Vercel auto-deploys frontend on push to `main`

### Cron Jobs (GitHub Actions)

The reminder engine runs daily at 8:00 AM IST (2:30 AM UTC) via a GitHub Actions workflow (`.github/workflows/reminder-cron.yml`). It calls the backend's `/internal/run-reminder-engine` endpoint.

Required GitHub Secrets:
- `PRODUCTION_API_URL` — Backend production URL
- `ADMIN_SECRET_KEY` — Admin key for internal endpoints

### Required Backend Environment Variables

All variables listed in `backend/envs/.env.production.example` must be set. The app will crash on startup if any are missing.

Order notification specific variables:
- `WHATSAPP_TEMPLATE_ORDER_FULFILLMENT_CHECK` (required): approved WhatsApp template name used when a user places an order.
- `ORDER_NOTIFICATION_PHONE` (optional): admin phone number that receives the order fulfillment check template. If unset, admin WhatsApp notification is skipped.

---

## Git Branching Strategy

```
main        ← Production-ready code. Auto-deploys to Render + Vercel.
dev         ← Active development. Feature branches merge here.
feature/*   ← Individual features (branched from dev).
bugfix/*    ← Bug fixes (branched from dev or main for hotfixes).
```

### Branch → Environment Mapping

| Branch | `APP_ENV` | Deploys To | Purpose |
|--------|-----------|------------|---------|
| `feature/*`, `dev` | `development` | Local / Dev services | Day-to-day development |
| `main` | `production` | Render (backend) + Vercel (frontend) | Live system |

### Workflow

1. **New feature**: Branch from `dev` → `feature/my-feature`
2. **Development done**: PR from `feature/*` → `dev` (CI runs lint + tests)
3. **Ready to ship**: PR from `dev` → `main` (auto-deploys to production)
4. **Hotfix**: Branch from `main` → `bugfix/fix-name`, PR back to `main` and cherry-pick to `dev`
