"""
PetCircle Phase 1 — Central Constants

All magic numbers and system-wide limits are defined here.
No other file should hardcode these values.
Import from this module to ensure single source of truth.
"""

# --- User & Pet Limits ---
# Maximum number of pets a single user can register.
# Enforced at the service layer during onboarding.
MAX_PETS_PER_USER: int = 5

# --- File Upload Limits ---
# Maximum file size in megabytes for document uploads.
MAX_UPLOAD_MB: int = 10

# Maximum file size in bytes, derived from MAX_UPLOAD_MB.
MAX_UPLOAD_BYTES: int = MAX_UPLOAD_MB * 1024 * 1024

# Maximum number of file uploads allowed per pet per day.
# Prevents abuse and controls storage costs.
MAX_UPLOADS_PER_PET_PER_DAY: int = 10

# Allowed MIME types for uploaded documents.
# Only images (JPEG, PNG) and PDF are accepted.
ALLOWED_MIME_TYPES: set[str] = {
    "image/jpeg",
    "image/png",
    "application/pdf",
}

# --- Timezone ---
# All date/time operations use Asia/Kolkata (IST).
# This is a system-wide constant — never use UTC or other zones.
SYSTEM_TIMEZONE: str = "Asia/Kolkata"

# --- Conflict Resolution ---
# Number of days before an unresolved conflict auto-resolves.
# After expiry, the system keeps the existing record (KEEP_EXISTING).
CONFLICT_EXPIRY_DAYS: int = 5

# --- Reminder Button Payload IDs ---
# These are the exact payload strings sent by WhatsApp interactive buttons.
# Never hardcode these strings elsewhere — always reference these constants.
REMINDER_DONE: str = "REMINDER_DONE"
REMINDER_SNOOZE_7: str = "REMINDER_SNOOZE_7"
# Number of days to push next_due_date forward when user snoozes a reminder.
REMINDER_SNOOZE_DAYS: int = 7
REMINDER_RESCHEDULE: str = "REMINDER_RESCHEDULE"
REMINDER_CANCEL: str = "REMINDER_CANCEL"

# --- Conflict Button Payload IDs ---
CONFLICT_USE_NEW: str = "CONFLICT_USE_NEW"
CONFLICT_KEEP_EXISTING: str = "CONFLICT_KEEP_EXISTING"

# --- Rate Limiting ---
# Maximum WhatsApp messages per phone number within the rolling window.
MAX_MESSAGES_PER_MINUTE: int = 20

# Rolling window duration in seconds for rate limiting.
RATE_LIMIT_WINDOW_SECONDS: int = 60

# --- OpenAI Model Configuration ---
# Extraction model for parsing uploaded documents into structured health data.
OPENAI_EXTRACTION_MODEL: str = "gpt-4.1"

# Query model for answering user questions grounded in pet records.
OPENAI_QUERY_MODEL: str = "gpt-4.1-mini"

# Temperature for extraction — deterministic output required.
OPENAI_EXTRACTION_TEMPERATURE: float = 0.0

# Max tokens for extraction response.
OPENAI_EXTRACTION_MAX_TOKENS: int = 1500

# --- Retry Configuration ---
# OpenAI retry backoff intervals in seconds.
OPENAI_RETRY_BACKOFFS: list[float] = [1.0, 2.0]

# WhatsApp retries — single retry only.
WHATSAPP_MAX_RETRIES: int = 1

# --- Dashboard Token ---
# Length in bytes for generating secure random dashboard tokens.
# 128-bit = 16 bytes, rendered as 32-char hex string.
DASHBOARD_TOKEN_BYTES: int = 16

# --- Health Score Weights ---
# Essential preventive items weight (e.g., vaccines, deworming).
HEALTH_SCORE_ESSENTIAL_WEIGHT: float = 0.9

# Complementary preventive items weight (e.g., dental, blood test).
HEALTH_SCORE_COMPLEMENTARY_WEIGHT: float = 0.1

# --- Supabase Storage ---
# Path template for uploaded files: {user_id}/{pet_id}/{filename}
# Enforced in the upload service — never construct paths manually elsewhere.
STORAGE_PATH_TEMPLATE: str = "{user_id}/{pet_id}/{filename}"

# --- Date Formats ---
# Accepted input date formats for parsing user-provided dates.
ACCEPTED_DATE_FORMATS: list[str] = [
    "%d/%m/%Y",      # DD/MM/YYYY
    "%d-%m-%Y",      # DD-MM-YYYY
    "%d %B %Y",      # 12 March 2024
    "%Y-%m-%d",      # ISO format
]

# Canonical storage format for all dates in the database.
DB_DATE_FORMAT: str = "%Y-%m-%d"
