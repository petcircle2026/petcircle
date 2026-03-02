#!/usr/bin/env bash
# Start the backend in development mode.
# Usage: bash scripts/run_dev.sh

set -euo pipefail

export APP_ENV="${APP_ENV:-development}"

echo "Starting PetCircle backend (APP_ENV=$APP_ENV)..."
uvicorn app.main:app --reload --port 8000
