"""
PetCircle Phase 1 — Date Utility (Module 18)

Accepts multiple date formats commonly used in India and converts
them to the canonical YYYY-MM-DD format for database storage.

Accepted formats:
    - DD/MM/YYYY  (e.g., 25/03/2024)
    - DD-MM-YYYY  (e.g., 25-03-2024)
    - DD Month YYYY (e.g., 12 March 2024)
    - YYYY-MM-DD  (ISO format)

All date operations use Asia/Kolkata timezone.
Raises clear validation errors if no format matches.
"""

from datetime import date, datetime
import pytz
from app.core.constants import ACCEPTED_DATE_FORMATS, DB_DATE_FORMAT, SYSTEM_TIMEZONE


# Timezone object for Asia/Kolkata — used for all date operations.
IST = pytz.timezone(SYSTEM_TIMEZONE)


def parse_date(raw_date: str) -> date:
    """
    Parse a user-provided date string into a Python date object.

    Tries each accepted format in order. Returns the first successful parse.
    Raises ValueError with a clear message if none of the formats match.

    Args:
        raw_date: The raw date string from user input or GPT extraction.

    Returns:
        A Python date object representing the parsed date.

    Raises:
        ValueError: If the date string does not match any accepted format.
            The error message lists all accepted formats for user guidance.
    """
    if not raw_date or not raw_date.strip():
        raise ValueError("Date string is empty. Please provide a valid date.")

    cleaned = raw_date.strip()

    # Try each accepted format in order.
    # Order matters: more specific formats (with separators) are tried first,
    # ISO format last as a catch-all for programmatic inputs.
    for fmt in ACCEPTED_DATE_FORMATS:
        try:
            parsed = datetime.strptime(cleaned, fmt)
            return parsed.date()
        except ValueError:
            continue

    # None of the formats matched — raise a clear error.
    accepted = ", ".join(ACCEPTED_DATE_FORMATS)
    raise ValueError(
        f"Invalid date format: '{raw_date}'. "
        f"Accepted formats: DD/MM/YYYY, DD-MM-YYYY, 12 March 2024, YYYY-MM-DD."
    )


def format_date_for_db(d: date) -> str:
    """
    Format a Python date object into the canonical database storage format.

    All dates in the database are stored as YYYY-MM-DD strings.

    Args:
        d: A Python date object to format.

    Returns:
        A string in YYYY-MM-DD format.
    """
    return d.strftime(DB_DATE_FORMAT)


def get_today_ist() -> date:
    """
    Get today's date in Asia/Kolkata timezone.

    All date comparisons in PetCircle use IST, not UTC.
    This function ensures consistent timezone handling across
    the preventive calculator, reminder engine, and conflict expiry.

    Returns:
        Today's date in Asia/Kolkata timezone.
    """
    return datetime.now(IST).date()
