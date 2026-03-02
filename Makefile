.PHONY: dev test lint seed frontend-dev frontend-build

# --- Backend ---

dev:
	cd backend && APP_ENV=development uvicorn app.main:app --reload --port 8000

test:
	cd backend && APP_ENV=test pytest tests/ -v

lint:
	cd backend && ruff check app/ tests/

lint-fix:
	cd backend && ruff check --fix app/ tests/

seed:
	cd backend && python scripts/seed_preventive_master.py

# --- Frontend ---

frontend-dev:
	cd frontend && npm run dev

frontend-build:
	cd frontend && npm run build

frontend-lint:
	cd frontend && npm run lint
