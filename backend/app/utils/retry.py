"""
PetCircle Phase 1 — Retry Utilities (Module 17)

Provides retry wrappers for external API calls (OpenAI, WhatsApp).
Each wrapper has a specific retry policy tuned to the service's
failure characteristics.

Retry policies:
    - OpenAI: 3 attempts with 1s, 2s backoff. Fail on 3rd attempt.
    - WhatsApp: 2 attempts (1 retry). Log failure, continue.
    - Database: No retry — failures indicate constraint violations
      or connection issues that should not be silently retried.

These utilities ensure external API failures are isolated and
do not crash the main application flow.
"""

import asyncio
import logging
from typing import TypeVar, Callable, Any
from app.core.constants import OPENAI_RETRY_BACKOFFS, WHATSAPP_MAX_RETRIES


logger = logging.getLogger(__name__)

T = TypeVar("T")


async def retry_openai_call(func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """
    Retry wrapper for OpenAI API calls.

    Retry policy:
        - Attempt 1: immediate
        - Attempt 2: after 1s backoff
        - Attempt 3: after 2s backoff
        - If all 3 fail, raise the last exception

    This policy handles transient OpenAI rate limits and timeouts.
    Permanent errors (invalid API key, malformed request) will still
    fail on the first attempt — retries only help with transient issues.

    Args:
        func: The async callable that makes the OpenAI API call.
        *args: Positional arguments passed to func.
        **kwargs: Keyword arguments passed to func.

    Returns:
        The result of the successful API call.

    Raises:
        Exception: The last exception if all retry attempts fail.
    """
    last_exception = None
    # Total attempts = 1 (initial) + len(backoffs) retries
    total_attempts = 1 + len(OPENAI_RETRY_BACKOFFS)

    for attempt in range(total_attempts):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            last_exception = e
            if attempt < len(OPENAI_RETRY_BACKOFFS):
                backoff = OPENAI_RETRY_BACKOFFS[attempt]
                logger.warning(
                    "OpenAI call failed (attempt %d/%d), retrying in %ss: %s",
                    attempt + 1, total_attempts, backoff, str(e)
                )
                await asyncio.sleep(backoff)
            else:
                # Final attempt failed — log and raise.
                logger.error(
                    "OpenAI call failed after %d attempts: %s",
                    total_attempts, str(e)
                )

    raise last_exception  # type: ignore[misc]


async def retry_whatsapp_call(func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """
    Retry wrapper for WhatsApp Cloud API calls.

    Retry policy:
        - Attempt 1: immediate
        - Attempt 2: immediate retry (no backoff)
        - If both fail, log the failure and return None
        - Never raises — WhatsApp failures must not crash the flow

    WhatsApp message delivery is best-effort. If a template message
    fails to send after 1 retry, the failure is logged but the
    application continues processing. This prevents WhatsApp outages
    from blocking the entire pipeline.

    Args:
        func: The async callable that makes the WhatsApp API call.
        *args: Positional arguments passed to func.
        **kwargs: Keyword arguments passed to func.

    Returns:
        The result of the successful API call, or None if all attempts fail.
    """
    total_attempts = 1 + WHATSAPP_MAX_RETRIES

    for attempt in range(total_attempts):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            if attempt < WHATSAPP_MAX_RETRIES:
                logger.warning(
                    "WhatsApp call failed (attempt %d/%d), retrying: %s",
                    attempt + 1, total_attempts, str(e)
                )
            else:
                # Final attempt failed — log error but do not raise.
                # WhatsApp failures must never crash the processing flow.
                logger.error(
                    "WhatsApp call failed after %d attempts. "
                    "Continuing without sending message: %s",
                    total_attempts, str(e)
                )

    return None
