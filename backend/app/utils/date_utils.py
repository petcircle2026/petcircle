"""
PetCircle Phase 1 — Date Utility (Module 18)

Accepts multiple date formats commonly used in India and converts
them to the canonical YYYY-MM-DD format for database storage.

Accepted formats:
    - DD/MM/YYYY, DD-MM-YYYY, DD.MM.YYYY
    - DD/MM/YY, DD-MM-YY
    - DD Month YYYY, DD Mon YYYY
    - Month DD, YYYY
    - YYYY-MM-DD (ISO format)
    - Month YYYY or MM/YYYY (day defaults to 1)

Falls back to OpenAI for ambiguous/unrecognized date strings.
All date operations use Asia/Kolkata timezone.
"""

import logging
import re
from datetime import date, datetime

import pytz

from app.core.constants import (
    ACCEPTED_DATE_FORMATS,
    DB_DATE_FORMAT,
    MONTH_YEAR_FORMATS,
    SYSTEM_TIMEZONE,
)

logger = logging.getLogger(__name__)

# Timezone object for Asia/Kolkata — used for all date operations.
IST = pytz.timezone(SYSTEM_TIMEZONE)


def parse_date(raw_date: str) -> date:
    """
    Parse a user-provided date string into a Python date object.

    Tries each accepted format in order, then month+year formats (day=1),
    then falls back to OpenAI for ambiguous inputs.

    Args:
        raw_date: The raw date string from user input or GPT extraction.

    Returns:
        A Python date object representing the parsed date.

    Raises:
        ValueError: If the date string cannot be parsed by any method.
    """
    if not raw_date or not raw_date.strip():
        raise ValueError("Date string is empty. Please provide a valid date.")

    cleaned = raw_date.strip()

    # Try each accepted full-date format in order.
    for fmt in ACCEPTED_DATE_FORMATS:
        try:
            parsed = datetime.strptime(cleaned, fmt)
            return parsed.date()
        except ValueError:
            continue

    # Try month+year formats — day defaults to 1.
    for fmt in MONTH_YEAR_FORMATS:
        try:
            parsed = datetime.strptime(cleaned, fmt)
            # strptime defaults day to 1, which is what we want.
            return parsed.date()
        except ValueError:
            continue

    # Try extracting just a year (e.g., "2022") — default to Jan 1.
    year_match = re.fullmatch(r"(\d{4})", cleaned)
    if year_match:
        year = int(year_match.group(1))
        if 1900 <= year <= 2100:
            return date(year, 1, 1)

    # None of the formats matched — raise error.
    raise ValueError(
        f"Invalid date format: '{raw_date}'. "
        f"Please use DD/MM/YYYY, DD-MM-YYYY, March 2024, or similar formats."
    )


async def parse_date_with_ai(raw_date: str) -> date:
    """
    Use OpenAI to parse an ambiguous date string into a Python date.

    Called as a fallback when standard format parsing fails.
    Uses gpt-4.1-mini for cost efficiency.

    Args:
        raw_date: The raw date string that couldn't be parsed.

    Returns:
        A Python date object.

    Raises:
        ValueError: If AI also cannot parse the date.
    """
    from openai import AsyncOpenAI
    from app.config import settings
    from app.core.constants import OPENAI_QUERY_MODEL

    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    try:
        response = await client.chat.completions.create(
            model=OPENAI_QUERY_MODEL,
            temperature=0.0,
            max_tokens=20,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a date parser. Extract the date from the user's input "
                        "and return ONLY the date in YYYY-MM-DD format. "
                        "If only month and year are given, use 01 as the day. "
                        "If only a year is given, use 01-01 as month and day. "
                        "If you cannot determine a valid date, respond with ERROR."
                    ),
                },
                {"role": "user", "content": raw_date},
            ],
        )

        result = response.choices[0].message.content.strip()
        if result == "ERROR":
            raise ValueError(f"AI could not parse date: '{raw_date}'")

        parsed = datetime.strptime(result, "%Y-%m-%d")
        return parsed.date()

    except ValueError:
        raise
    except Exception as e:
        logger.error("AI date parsing failed for '%s': %s", raw_date, str(e))
        raise ValueError(f"Could not parse date: '{raw_date}'")


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
