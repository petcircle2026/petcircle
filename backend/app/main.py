"""
PetCircle Phase 1 — FastAPI Application Entry Point

This is the main application module. It initializes the FastAPI app,
validates environment configuration at startup, and registers routers.

No business logic lives here — only app bootstrapping.
"""

from fastapi import FastAPI
from app.config import settings
from app.routers import webhook, admin, internal, dashboard


# Application initialization.
# Settings are validated at import time (app/config.py).
# If any required env var is missing, the app crashes before reaching this point.
app = FastAPI(
    title="PetCircle API",
    description="WhatsApp-based preventive pet health system — Phase 1",
    version="1.0.0",
)

# --- Register Routers ---
# Webhook router: /webhook/whatsapp (GET verify, POST messages)
app.include_router(webhook.router)
# Admin router: /admin/* (all routes require X-ADMIN-KEY header)
app.include_router(admin.router)
# Internal router: /internal/* (cron jobs, requires X-ADMIN-KEY header)
app.include_router(internal.router)
# Dashboard router: /dashboard/{token} (token-based access, no auth header)
app.include_router(dashboard.router)


@app.get("/health")
async def health_check():
    """
    Basic health check endpoint.

    Returns 200 OK to confirm the service is running
    and environment configuration is valid.
    Used by Render for uptime monitoring.
    """
    return {
        "status": "healthy",
        "timezone": settings.TIMEZONE,
    }
