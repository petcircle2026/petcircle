# PetCircle — Preventive Pet Health System

WhatsApp-based preventive health tracking for pets. Built with the **WAT framework** (Workflows, Agents, Tools).

## Repository Structure

```
pet-circle/
├── .claude/          # Architecture specs (CLAUDE.md, MODULES.md, SEQUENCE.md)
├── workflows/        # WAT Layer 1: Markdown SOPs for each major flow
├── backend/          # Python + FastAPI (WAT Layer 3: Tools)
├── frontend/         # Next.js + Tailwind (Dashboard)
├── fixtures/         # Sample data and test reports
└── docs/             # Architecture and setup documentation
```

## Quick Start

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt -r requirements-dev.txt

# Copy and fill in your dev credentials
cp envs/.env.example envs/.env.development

# Run
APP_ENV=development uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
cp .env.example .env.local

npm run dev
```

### Using Make

```bash
make dev          # Start backend in dev mode
make test         # Run backend tests
make lint         # Lint backend code
make frontend-dev # Start frontend dev server
```

## Architecture

See [docs/architecture.md](docs/architecture.md) for the full system overview.

See [docs/environment-setup.md](docs/environment-setup.md) for dev/test/prod configuration.

## Tech Stack

| Component | Technology |
|-----------|------------|
| Backend | Python 3.11 + FastAPI |
| Messaging | WhatsApp Cloud API |
| AI | OpenAI GPT (gpt-4.1) |
| Database | Supabase (PostgreSQL) |
| Frontend | Next.js 14 + Tailwind |
| Hosting | Render |
