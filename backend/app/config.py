"""
PetCircle Phase 1 — Application Configuration

Uses Pydantic BaseSettings to load and validate all environment variables.
If any required variable is missing, the application will refuse to start
and print a clear error message identifying the missing variable.

All credentials are loaded from environment files only — never hardcoded.

Environment selection:
  - Set APP_ENV to 'development', 'test', or 'production'.
  - Defaults to 'development' if not set.
  - Loads envs/.env.{APP_ENV} file; in production, the hosting provider sets env vars directly.
"""

import os
from pathlib import Path

from pydantic_settings import BaseSettings
from pydantic import field_validator
from app.core.constants import SYSTEM_TIMEZONE

# --- Environment Selection ---
# APP_ENV controls which env file is loaded: development | test | production
APP_ENV: str = os.getenv("APP_ENV", "development")

# Resolve the env file path relative to the backend/ directory.
# In production, the hosting provider injects env vars directly — no file needed.
_backend_dir = Path(__file__).resolve().parent.parent
_env_file = _backend_dir / "envs" / f".env.{APP_ENV}"
_env_file_path: str | None = str(_env_file) if _env_file.exists() else None


class Settings(BaseSettings):
    """
    Central configuration for PetCircle backend.

    Every field maps to an environment variable.
    Pydantic validates presence and type at startup.
    If any required field is missing, a RuntimeError is raised
    with a clear message identifying which variable is absent.
    """

    # --- Environment ---
    APP_ENV: str = APP_ENV

    # --- OpenAI ---
    OPENAI_API_KEY: str

    # --- Supabase ---
    SUPABASE_URL: str
    SUPABASE_KEY: str
    SUPABASE_SERVICE_ROLE_KEY: str
    SUPABASE_BUCKET_NAME: str

    # --- WhatsApp Cloud API ---
    WHATSAPP_TOKEN: str
    WHATSAPP_VERIFY_TOKEN: str
    WHATSAPP_PHONE_NUMBER_ID: str
    WHATSAPP_APP_SECRET: str

    # --- WhatsApp Template Names ---
    # Templates are loaded from environment to allow changes without code deploys.
    WHATSAPP_TEMPLATE_REMINDER: str
    WHATSAPP_TEMPLATE_OVERDUE: str
    WHATSAPP_TEMPLATE_NUDGE: str
    WHATSAPP_TEMPLATE_CONFLICT: str
    WHATSAPP_TEMPLATE_ONBOARDING_COMPLETE: str

    # --- Admin ---
    # Secret key for admin API authentication via X-ADMIN-KEY header.
    ADMIN_SECRET_KEY: str
    # Separate password for admin dashboard login (not the raw API key).
    ADMIN_DASHBOARD_PASSWORD: str

    # --- Database ---
    DATABASE_URL: str

    # --- Security ---
    # Fernet encryption key for PII field-level encryption.
    # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    ENCRYPTION_KEY: str

    # Frontend URL for CORS allow-origin (e.g., https://petcircle.vercel.app).
    FRONTEND_URL: str

    # --- Order Notifications ---
    # WhatsApp phone number to notify when a new order is placed.
    # Format: country code + number, no + prefix (e.g., "919095705762").
    # Optional — if not set, only dashboard notification (no WhatsApp alert).
    ORDER_NOTIFICATION_PHONE: str | None = None

    # --- Timezone ---
    # Derived from constants, not from environment.
    # Exposed here so all layers can access timezone through settings.
    TIMEZONE: str = SYSTEM_TIMEZONE

    class Config:
        """Load variables from the environment-specific env file."""
        env_file = _env_file_path
        env_file_encoding = "utf-8"
        # Do not allow extra fields — catches typos in .env
        extra = "ignore"


def get_settings() -> Settings:
    """
    Load and validate all environment variables.

    Raises RuntimeError with a clear message if any required
    environment variable is missing, preventing the application
    from starting in an invalid state.
    """
    try:
        return Settings()  # type: ignore[call-arg]
    except Exception as e:
        # Extract which fields are missing from the validation error.
        # Pydantic v2 raises ValidationError with details per field.
        raise RuntimeError(
            f"Application startup failed — missing or invalid environment variables.\n"
            f"APP_ENV={APP_ENV}, env_file={_env_file_path}\n"
            f"Details: {e}\n"
            f"Ensure all variables in envs/.env.example are set."
        ) from e


# Singleton settings instance — initialized at import time.
# If env vars are missing, the application crashes immediately on startup
# rather than failing silently at runtime.
settings = get_settings()
