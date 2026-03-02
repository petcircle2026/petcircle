# PetCircle — Environment Setup Guide

## Environment Strategy

PetCircle uses `APP_ENV` to select the configuration file:

| Environment | `APP_ENV` | Env File | Purpose |
|-------------|-----------|----------|---------|
| Development | `development` | `backend/envs/.env.development` | Local dev with real or test APIs |
| Test | `test` | `backend/envs/.env.test` | Automated tests with mock values |
| Production | `production` | *(none — Render injects vars)* | Live system |

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

## Production Setup (Render)

1. Connect your GitHub repo to Render
2. Use `render.yaml` as the blueprint
3. Set all environment variables in the Render dashboard (see `backend/envs/.env.production.example` for the list)
4. Render auto-deploys on push to `main`

### Required Render Environment Variables

All variables listed in `backend/envs/.env.production.example` must be set. The app will crash on startup if any are missing.

### Cron Job

The reminder engine runs daily at 8:00 AM IST (2:30 AM UTC). This is configured in `render.yaml` as a cron service.
