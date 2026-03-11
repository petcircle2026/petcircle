"""
PetCircle Phase 1 — Central Constants

All magic numbers and system-wide limits are defined here.
No other file should hardcode these values.
Import from this module to ensure single source of truth.
"""

# --- Application Branding ---
APP_BRAND_NAME: str = "PetCircle"
APP_BRAND_SLUG: str = "petcircle"
APP_BRAND_PAW_ICON: str = "🐾"
APP_API_TITLE: str = f"{APP_BRAND_NAME} API"
APP_TAGLINE: str = f"{APP_BRAND_NAME} — Preventive Pet Health System"
APP_ADMIN_TITLE: str = f"{APP_BRAND_NAME} Admin"
APP_WELCOME_HEADING: str = f"Hey there! Welcome to *{APP_BRAND_NAME}* {APP_BRAND_PAW_ICON}"
APP_RETURNING_HEADING: str = f"Welcome back to *{APP_BRAND_NAME}* {APP_BRAND_PAW_ICON}"

# --- User & Pet Limits ---
# Maximum number of pets a single user can register.
# Enforced at the service layer during onboarding.
MAX_PETS_PER_USER: int = 5

# --- Post-Onboarding Document Upload Window ---
# Duration in seconds for the guided upload window after onboarding completes.
# User is prompted to upload medical records during this window.
DOC_UPLOAD_WINDOW_SECONDS: int = 300  # 5 minutes

# --- File Upload Limits ---
# Maximum file size in megabytes for document uploads.
MAX_UPLOAD_MB: int = 10

# Maximum file size in bytes, derived from MAX_UPLOAD_MB.
MAX_UPLOAD_BYTES: int = MAX_UPLOAD_MB * 1024 * 1024

# Maximum number of file uploads allowed per pet per day.
# Prevents abuse and controls storage costs.
MAX_UPLOADS_PER_PET_PER_DAY: int = 10

# Maximum number of pending (unprocessed) documents allowed per pet at a time.
# If a pet already has this many pending documents, new uploads are rejected
# until existing ones finish extraction. Prevents queue flooding.
MAX_PENDING_DOCS_PER_PET: int = 5

# Maximum number of concurrent background extraction tasks system-wide.
# Sized to allow multiple pet batches to extract in parallel while
# staying within DB pool limits (pool_size=10, max_overflow=10).
# Each extraction holds a DB session for the GPT call duration (~5-15s).
MAX_CONCURRENT_EXTRACTIONS: int = 5

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

# Query-specific OpenAI settings — separated from extraction to allow
# independent tuning (e.g., slightly higher temperature for natural responses).
OPENAI_QUERY_TEMPERATURE: float = 0.0
OPENAI_QUERY_MAX_TOKENS: int = 1500

# --- Retry Configuration ---
# OpenAI retry backoff intervals in seconds.
OPENAI_RETRY_BACKOFFS: list[float] = [1.0, 2.0]

# WhatsApp retries — single retry only.
WHATSAPP_MAX_RETRIES: int = 1

# --- Dashboard Token ---
# Length in bytes for generating secure random dashboard tokens.
# 128-bit = 16 bytes, rendered as 32-char hex string.
DASHBOARD_TOKEN_BYTES: int = 16

# Number of days before a dashboard token expires.
# After expiry, the user can regenerate by typing "dashboard" in WhatsApp.
DASHBOARD_TOKEN_EXPIRY_DAYS: int = 30

# --- Health Score Weights ---
# Essential preventive items weight (e.g., vaccines, deworming).
HEALTH_SCORE_ESSENTIAL_WEIGHT: float = 0.9

# Complementary preventive items weight (e.g., dental, blood test).
HEALTH_SCORE_COMPLEMENTARY_WEIGHT: float = 0.1

# --- Supabase Storage ---
# Path template for uploaded files: {user_id}/{pet_id}/{filename}
# Enforced in the upload service — never construct paths manually elsewhere.
STORAGE_PATH_TEMPLATE: str = "{user_id}/{pet_id}/{filename}"

# --- Greeting Detection ---
# Shared set of greetings used by both onboarding and message router
# to detect casual greetings and avoid routing them to GPT.
GREETINGS: frozenset[str] = frozenset({
    "hi", "hello", "hey", "hii", "hiii", "yo", "sup",
    "hola", "namaste", "good morning", "good evening",
    "good afternoon", "gm", "start", "restart",
})

# --- Common Acknowledgment / Farewell Messages ---
# Messages that should get canned responses, not GPT calls.
ACKNOWLEDGMENTS: frozenset[str] = frozenset({
    "thanks", "thank you", "thankyou", "thx", "ty",
    "ok", "okay", "got it", "cool", "great", "nice",
    "awesome", "perfect", "sure", "alright",
})

FAREWELLS: frozenset[str] = frozenset({
    "bye", "goodbye", "good bye", "see you", "cya", "later",
})

HELP_COMMANDS: frozenset[str] = frozenset({
    "help", "menu", "commands", "what can you do",
})

# --- Order Flow ---
# Commands that trigger the product ordering flow.
ORDER_COMMANDS: frozenset[str] = frozenset({
    "order", "shop", "buy",
})

# Button payload IDs for order category selection.
ORDER_CAT_MEDICINES: str = "ORDER_CAT_MEDICINES"
ORDER_CAT_FOOD: str = "ORDER_CAT_FOOD"
ORDER_CAT_SUPPLEMENTS: str = "ORDER_CAT_SUPPLEMENTS"

# Button payload IDs for order confirmation.
ORDER_CONFIRM: str = "ORDER_CONFIRM"
ORDER_CANCEL: str = "ORDER_CANCEL"

# Sets for routing in message_router.
ORDER_CATEGORY_PAYLOADS: frozenset[str] = frozenset({
    ORDER_CAT_MEDICINES, ORDER_CAT_FOOD, ORDER_CAT_SUPPLEMENTS,
})

ORDER_CONFIRM_PAYLOADS: frozenset[str] = frozenset({
    ORDER_CONFIRM, ORDER_CANCEL,
})

# Prefixes for dynamic order fulfillment payloads sent to admin number.
# Full payload format:
#   ORDER_FULFILL_YES:{order_id}
#   ORDER_FULFILL_NO:{order_id}
ORDER_FULFILL_YES_PREFIX: str = "ORDER_FULFILL_YES:"
ORDER_FULFILL_NO_PREFIX: str = "ORDER_FULFILL_NO:"

# Map button payload → database category value.
ORDER_CATEGORY_MAP: dict[str, str] = {
    ORDER_CAT_MEDICINES: "medicines",
    ORDER_CAT_FOOD: "food_nutrition",
    ORDER_CAT_SUPPLEMENTS: "supplements",
}

# Map database category → display label for WhatsApp messages.
ORDER_CATEGORY_LABELS: dict[str, str] = {
    "medicines": "Medicines",
    "food_nutrition": "Food & Nutrition",
    "supplements": "Supplements",
}

# --- Pet Weight ---
# Maximum allowed pet weight in kg. Anything above is rejected.
MAX_PET_WEIGHT_KG: float = 100.0

# --- Date Formats ---
# Accepted input date formats for parsing user-provided dates.
ACCEPTED_DATE_FORMATS: list[str] = [
    "%d/%m/%Y",      # DD/MM/YYYY
    "%d-%m-%Y",      # DD-MM-YYYY
    "%d.%m.%Y",      # DD.MM.YYYY
    "%d %B %Y",      # 12 March 2024
    "%d %b %Y",      # 12 Mar 2024
    "%d %B %y",      # 12 March 24
    "%d %b %y",      # 12 Mar 24
    "%d-%b-%Y",      # 29-Jan-2025
    "%d-%b-%y",      # 29-Jan-25
    "%B %d, %Y",     # March 12, 2024
    "%b %d, %Y",     # Mar 12, 2024
    "%Y-%m-%d",      # ISO format
    "%d/%m/%y",      # DD/MM/YY
    "%d-%m-%y",      # DD-MM-YY
]

# Formats for month+year only (day defaults to 1).
MONTH_YEAR_FORMATS: list[str] = [
    "%B %Y",         # March 2024
    "%b %Y",         # Mar 2024
    "%m/%Y",         # 03/2024
    "%m-%Y",         # 03-2024
]

# Canonical storage format for all dates in the database.
DB_DATE_FORMAT: str = "%Y-%m-%d"

# --- Document Categories ---
# Categories assigned by GPT extraction to classify uploaded documents.
# Used for grouping in the dashboard and filtering.
DOCUMENT_CATEGORIES: list[str] = [
    "Vaccination",
    "Prescription",
    "Diagnostic",
    "Other",
]
