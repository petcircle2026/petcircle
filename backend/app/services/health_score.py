"""
PetCircle Phase 1 — Health Score Engine (Module 12)

Computes a pet's health score based on the ratio of up-to-date
preventive records across essential and complementary categories.

Formula:
    Score = (
        (E_done / E_total) * HEALTH_SCORE_ESSENTIAL_WEIGHT +
        (C_done / C_total) * HEALTH_SCORE_COMPLEMENTARY_WEIGHT
    ) * 100

    Where:
        E_done = essential records with status 'up_to_date'
        E_total = total essential records (non-cancelled)
        C_done = complementary ('complete' category) records with status 'up_to_date'
        C_total = total complementary records (non-cancelled)

    Weights (from constants — never hardcoded):
        HEALTH_SCORE_ESSENTIAL_WEIGHT = 0.9
        HEALTH_SCORE_COMPLEMENTARY_WEIGHT = 0.1

    Result rounded to nearest integer.

Edge cases:
    - If E_total is 0: essential ratio defaults to 0.
    - If C_total is 0: complementary ratio defaults to 0.
    - If no records exist at all: score is 0.
    - Cancelled records are excluded from both numerator and denominator.

Rules:
    - Weights always from constants.py — never hardcoded.
    - Category classification always from preventive_master DB table.
    - No partial logic — full formula always applied.
"""

import logging
from uuid import UUID
from sqlalchemy.orm import Session
from app.models.preventive_record import PreventiveRecord
from app.models.preventive_master import PreventiveMaster
from app.core.constants import (
    HEALTH_SCORE_ESSENTIAL_WEIGHT,
    HEALTH_SCORE_COMPLEMENTARY_WEIGHT,
)


logger = logging.getLogger(__name__)


def compute_health_score(db: Session, pet_id: UUID) -> dict:
    """
    Compute the health score for a pet.

    Calculates the weighted ratio of up-to-date preventive records
    across essential and complementary (complete) categories.

    The score weights are from constants:
        - HEALTH_SCORE_ESSENTIAL_WEIGHT (0.9) for essential items.
        - HEALTH_SCORE_COMPLEMENTARY_WEIGHT (0.1) for complementary items.

    Category classification comes from preventive_master.category in DB:
        - 'essential' → essential category
        - 'complete' → complementary category

    Cancelled records are excluded from the calculation entirely.
    Records with status 'up_to_date' count as "done" in the numerator.

    Args:
        db: SQLAlchemy database session.
        pet_id: UUID of the pet to compute score for.

    Returns:
        Dictionary with score details:
            - score: integer health score (0-100)
            - essential_done: count of up-to-date essential records
            - essential_total: total non-cancelled essential records
            - complementary_done: count of up-to-date complementary records
            - complementary_total: total non-cancelled complementary records
    """
    # Load all non-cancelled preventive records for this pet,
    # joined with preventive_master for category classification.
    records = (
        db.query(PreventiveRecord, PreventiveMaster.category)
        .join(
            PreventiveMaster,
            PreventiveRecord.preventive_master_id == PreventiveMaster.id,
        )
        .filter(
            PreventiveRecord.pet_id == pet_id,
            # Exclude cancelled records from score calculation.
            PreventiveRecord.status != "cancelled",
        )
        .all()
    )

    # --- Count essential and complementary records ---
    # Category is determined by preventive_master.category from DB.
    # 'essential' maps to essential weight.
    # 'complete' maps to complementary weight.
    essential_done = 0
    essential_total = 0
    complementary_done = 0
    complementary_total = 0

    for record, category in records:
        if category == "essential":
            essential_total += 1
            if record.status == "up_to_date":
                essential_done += 1
        elif category == "complete":
            # 'complete' category in DB = complementary in score formula.
            complementary_total += 1
            if record.status == "up_to_date":
                complementary_done += 1

    # --- Compute weighted ratios ---
    # If a category has no records, its ratio defaults to 0.
    # This prevents division by zero.
    essential_ratio = (
        essential_done / essential_total if essential_total > 0 else 0.0
    )
    complementary_ratio = (
        complementary_done / complementary_total if complementary_total > 0 else 0.0
    )

    # --- Apply formula ---
    # Weights from constants — never hardcoded.
    raw_score = (
        essential_ratio * HEALTH_SCORE_ESSENTIAL_WEIGHT
        + complementary_ratio * HEALTH_SCORE_COMPLEMENTARY_WEIGHT
    ) * 100

    # Round to nearest integer as specified.
    score = round(raw_score)

    logger.info(
        "Health score computed: pet_id=%s, score=%d, "
        "essential=%d/%d, complementary=%d/%d",
        str(pet_id),
        score,
        essential_done,
        essential_total,
        complementary_done,
        complementary_total,
    )

    return {
        "score": score,
        "essential_done": essential_done,
        "essential_total": essential_total,
        "complementary_done": complementary_done,
        "complementary_total": complementary_total,
    }
