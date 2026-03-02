"""
PetCircle Phase 1 — FastAPI Application Entry Point

This is the main application module. It initializes the FastAPI app,
validates environment configuration at startup, registers routers,
and configures security middleware.

No business logic lives here — only app bootstrapping.
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.routers import webhook, admin, internal, dashboard


# Application initialization.
# Settings are validated at import time (app/config.py).
# If any required env var is missing, the app crashes before reaching this point.
# Swagger/redoc disabled in production to avoid exposing full API schema.
app = FastAPI(
    title="PetCircle API",
    description="WhatsApp-based preventive pet health system — Phase 1",
    version="1.0.0",
    docs_url=None if settings.APP_ENV == "production" else "/docs",
    redoc_url=None if settings.APP_ENV == "production" else "/redoc",
    openapi_url=None if settings.APP_ENV == "production" else "/openapi.json",
)

# --- CORS Middleware ---
# Restrict cross-origin requests to the frontend dashboard URL only.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL],
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Content-Type", "X-ADMIN-KEY"],
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Add security headers to all HTTP responses."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = "default-src 'self'"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    # Prevent browser/CDN caching of API responses containing sensitive data.
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return response


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
    Used for uptime monitoring.
    """
    return {
        "status": "healthy",
        "timezone": settings.TIMEZONE,
    }
