"""
PetCircle Phase 1 — In-Memory Rate Limiter

Enforces per-key rate limiting using a sliding window algorithm.
Used for WhatsApp messages (per phone number), dashboard (per IP),
and admin endpoints (per IP).

Implementation:
    - Tracks timestamps of recent requests per key in a deque.
    - On each check, expired timestamps are evicted.
    - If the count exceeds the limit, the request is rejected.

Limitations:
    - In-memory only — resets on server restart.
    - Not shared across multiple worker processes.
    - Sufficient for Phase 1 single-process deployment on Render.
"""

import logging
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from app.core.constants import MAX_MESSAGES_PER_MINUTE, RATE_LIMIT_WINDOW_SECONDS

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Sliding window rate limiter keyed by arbitrary string.

    Tracks request timestamps in a deque per key. Expired entries
    are pruned on each check to keep memory bounded.
    """

    def __init__(
        self,
        max_requests: int = MAX_MESSAGES_PER_MINUTE,
        window_seconds: int = RATE_LIMIT_WINDOW_SECONDS,
    ):
        """
        Initialize the rate limiter.

        Args:
            max_requests: Maximum allowed requests within the window.
            window_seconds: Rolling window duration in seconds.
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, deque] = defaultdict(deque)

    def check_rate_limit(self, key: str) -> bool:
        """
        Check whether a request from the given key is allowed.

        Evicts expired timestamps, then checks if the count is under the limit.
        If allowed, records the current timestamp.

        Args:
            key: The rate limit key (phone number, IP address, etc.).

        Returns:
            True if the request is allowed, False if rate-limited.
        """
        now = time.monotonic()
        window_start = now - self.window_seconds

        # Evict expired timestamps
        timestamps = self._requests[key]
        while timestamps and timestamps[0] < window_start:
            timestamps.popleft()

        if len(timestamps) >= self.max_requests:
            return False

        timestamps.append(now)
        return True


# --- Singleton instances ---

# WhatsApp message rate limiter — 20 requests/min per phone number.
rate_limiter = RateLimiter()

# Dashboard endpoint rate limiter — 30 requests/min per IP.
# Protects against brute-force and abuse on token-based endpoints.
dashboard_rate_limiter = RateLimiter(max_requests=30, window_seconds=60)

# Admin endpoint rate limiter — 10 requests/min per IP.
# Stricter limit to protect admin key brute-force attempts.
admin_rate_limiter = RateLimiter(max_requests=10, window_seconds=60)


def _get_client_ip(request: Request) -> str:
    """
    Extract the client IP from a FastAPI request.

    Uses X-Forwarded-For header if present (behind reverse proxy),
    otherwise falls back to the direct client host.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        # X-Forwarded-For can contain multiple IPs; the first is the client.
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def check_dashboard_rate_limit(request: Request) -> None:
    """
    FastAPI dependency that enforces IP-based rate limiting on dashboard routes.

    Raises HTTPException 429 if the client IP exceeds 30 requests/minute.
    """
    client_ip = _get_client_ip(request)
    if not dashboard_rate_limiter.check_rate_limit(client_ip):
        logger.warning("Dashboard rate limit exceeded for IP=%s", client_ip)
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please try again later.",
        )


async def check_admin_rate_limit(request: Request) -> None:
    """
    FastAPI dependency that enforces IP-based rate limiting on admin routes.

    Raises HTTPException 429 if the client IP exceeds 10 requests/minute.
    """
    client_ip = _get_client_ip(request)
    if not admin_rate_limiter.check_rate_limit(client_ip):
        logger.warning("Admin rate limit exceeded for IP=%s", client_ip)
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please try again later.",
        )
