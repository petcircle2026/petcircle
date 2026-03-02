"""
PetCircle Phase 1 — Dashboard Router (Module 13)

Provides tokenized access to pet health dashboards. Users receive
a secure random token via WhatsApp that grants read/write access
to their pet's dashboard.

Routes:
    GET  /dashboard/{token}          — Full dashboard data.
    PATCH /dashboard/{token}/weight  — Update pet weight.
    PATCH /dashboard/{token}/preventive — Update preventive record date.

Security:
    - Token-based access — no login required for Phase 1.
    - Token validated per-request (exists + not revoked).
    - No internal IDs exposed in responses.
    - All errors return generic messages to prevent information leakage.

Rules:
    - No bucket hardcoding — file paths are storage-relative.
    - Recalculation triggered after any data update.
    - Pending reminders invalidated when dates change.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.database import get_db
from app.core.rate_limiter import check_dashboard_rate_limit
from app.services.dashboard_service import (
    get_dashboard_data,
    update_pet_weight,
    update_preventive_date,
)
from app.utils.date_utils import parse_date


logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/dashboard",
    tags=["dashboard"],
    dependencies=[Depends(check_dashboard_rate_limit)],
)


class WeightUpdateRequest(BaseModel):
    """
    Request body for updating pet weight.

    Fields:
        weight: New weight in kg (positive number, max 2 decimal places).
    """

    weight: float = Field(
        ...,
        gt=0,
        le=999.99,
        description="New weight in kg (positive, max 999.99)",
    )


class PreventiveDateUpdateRequest(BaseModel):
    """
    Request body for updating a preventive record's last done date.

    Fields:
        item_name: Name of the preventive item (must match preventive_master).
        last_done_date: New date string (accepted formats from date_utils).
    """

    item_name: str = Field(
        ...,
        min_length=1,
        description="Preventive item name (e.g., 'Rabies Vaccine')",
    )
    last_done_date: str = Field(
        ...,
        min_length=1,
        description="New last done date (DD/MM/YYYY, DD-MM-YYYY, "
                    "12 March 2024, or YYYY-MM-DD)",
    )


@router.get("/{token}")
def dashboard_get(
    token: str,
    response: Response,
    db: Session = Depends(get_db),
):
    """
    Retrieve full dashboard data for a pet via access token.

    Returns pet profile, preventive records, reminders, documents,
    and health score. No internal IDs are exposed.

    Token validation:
        - Token must exist in dashboard_tokens table.
        - Token must not be revoked.
        - Token must not be expired.

    Cache-Control: no-store prevents browser/CDN caching of sensitive pet data.

    Args:
        token: Dashboard access token from URL path.
        response: FastAPI Response object for setting headers.
        db: SQLAlchemy database session (injected).

    Returns:
        Complete dashboard data dictionary.

    Raises:
        HTTPException 404: If token is invalid, revoked, or expired.
    """
    try:
        data = get_dashboard_data(db, token)
        # Prevent caching of sensitive pet health data.
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        return data
    except ValueError as e:
        # Generic error message — do not leak internal details.
        logger.warning(
            "Dashboard access failed: token=%s..., error=%s",
            token[:8] if len(token) >= 8 else token,
            str(e),
        )
        raise HTTPException(
            status_code=404,
            detail="Dashboard not found or link has expired.",
        )


@router.patch("/{token}/weight")
def dashboard_update_weight(
    token: str,
    body: WeightUpdateRequest,
    db: Session = Depends(get_db),
):
    """
    Update pet weight via dashboard token.

    Weight is a simple field update — no recalculation needed.

    Args:
        token: Dashboard access token from URL path.
        body: WeightUpdateRequest with new weight value.
        db: SQLAlchemy database session (injected).

    Returns:
        Confirmation dictionary with old and new weight.

    Raises:
        HTTPException 404: If token is invalid or pet not found.
    """
    try:
        result = update_pet_weight(db, token, body.weight)
        return result
    except ValueError as e:
        logger.warning(
            "Dashboard weight update failed: token=%s..., error=%s",
            token[:8] if len(token) >= 8 else token,
            str(e),
        )
        raise HTTPException(
            status_code=404,
            detail="Dashboard not found or link has expired.",
        )


@router.patch("/{token}/preventive")
def dashboard_update_preventive(
    token: str,
    body: PreventiveDateUpdateRequest,
    db: Session = Depends(get_db),
):
    """
    Update a preventive record's last done date via dashboard token.

    Triggers full recalculation:
        - next_due_date recalculated from recurrence_days (DB).
        - status recalculated based on new next_due_date.
        - Pending reminders for old due date are invalidated.

    Date format validation uses parse_date() from date_utils,
    which accepts DD/MM/YYYY, DD-MM-YYYY, DD Month YYYY, and YYYY-MM-DD.

    Args:
        token: Dashboard access token from URL path.
        body: PreventiveDateUpdateRequest with item name and new date.
        db: SQLAlchemy database session (injected).

    Returns:
        Confirmation dictionary with updated record details.

    Raises:
        HTTPException 400: If date format is invalid.
        HTTPException 404: If token invalid or record not found.
    """
    # --- Parse and validate the date ---
    # parse_date raises ValueError for invalid formats.
    try:
        new_date = parse_date(body.last_done_date)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid date format. Use DD/MM/YYYY, DD-MM-YYYY, or YYYY-MM-DD.",
        )

    try:
        result = update_preventive_date(
            db, token, body.item_name, new_date
        )
        return result
    except ValueError as e:
        logger.warning(
            "Dashboard preventive update failed: token=%s..., "
            "item=%s, error=%s",
            token[:8] if len(token) >= 8 else token,
            body.item_name,
            str(e),
        )
        raise HTTPException(
            status_code=404,
            detail="Dashboard not found or record not found.",
        )
