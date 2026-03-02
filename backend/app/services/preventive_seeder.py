"""
PetCircle Phase 1 — Preventive Master Seeder (Module 6)

Seeds the frozen preventive master table with the 8 standard
preventive health items for dogs and cats.

Rules:
    - Insert only if table is empty (idempotent — safe to re-run).
    - Enforce UNIQUE(item_name, species) via the table constraint.
    - All recurrence values are stored in the DB, never hardcoded in
      application logic — the seeder is the only place these appear.
    - This table is frozen after seeding. No runtime modifications.

Items seeded:
    1. Rabies Vaccine (dog + cat)
    2. Core Vaccine (dog)
    3. Feline Core (cat)
    4. Deworming (dog + cat)
    5. Tick/Flea (dog + cat)
    6. Annual Checkup (dog + cat)
    7. Preventive Blood Test (dog + cat)
    8. Dental Check (dog + cat)
"""

import logging
from sqlalchemy.orm import Session
from app.models.preventive_master import PreventiveMaster


logger = logging.getLogger(__name__)


# --- Frozen Preventive Master Data ---
# This is the ONLY place recurrence values are defined.
# All application logic must read recurrence_days from the DB.
#
# Structure per entry:
#   item_name, category, species, recurrence_days,
#   medicine_dependent, reminder_before_days, overdue_after_days
#
# Species "both" is expanded into separate "dog" and "cat" rows
# to satisfy the UNIQUE(item_name, species) constraint cleanly.
SEED_DATA: list[dict] = [
    # --- Rabies Vaccine ---
    # Essential for both dogs and cats. Annual recurrence (365 days).
    # Reminder 30 days before due, overdue after 7 days past due.
    {
        "item_name": "Rabies Vaccine",
        "category": "essential",
        "species": "dog",
        "recurrence_days": 365,
        "medicine_dependent": False,
        "reminder_before_days": 30,
        "overdue_after_days": 7,
    },
    {
        "item_name": "Rabies Vaccine",
        "category": "essential",
        "species": "cat",
        "recurrence_days": 365,
        "medicine_dependent": False,
        "reminder_before_days": 30,
        "overdue_after_days": 7,
    },
    # --- Core Vaccine (Dogs only) ---
    # Essential. Covers DHPP (Distemper, Hepatitis, Parvovirus, Parainfluenza).
    # Annual recurrence. Reminder 30 days before, overdue after 7 days.
    {
        "item_name": "Core Vaccine",
        "category": "essential",
        "species": "dog",
        "recurrence_days": 365,
        "medicine_dependent": False,
        "reminder_before_days": 30,
        "overdue_after_days": 7,
    },
    # --- Feline Core (Cats only) ---
    # Essential. Covers FVRCP (Feline Viral Rhinotracheitis, Calicivirus, Panleukopenia).
    # Annual recurrence. Reminder 30 days before, overdue after 7 days.
    {
        "item_name": "Feline Core",
        "category": "essential",
        "species": "cat",
        "recurrence_days": 365,
        "medicine_dependent": False,
        "reminder_before_days": 30,
        "overdue_after_days": 7,
    },
    # --- Deworming ---
    # Essential for both dogs and cats. Quarterly (90 days).
    # Medicine-dependent — specific product matters.
    # Reminder 7 days before, overdue after 7 days.
    {
        "item_name": "Deworming",
        "category": "essential",
        "species": "dog",
        "recurrence_days": 90,
        "medicine_dependent": True,
        "reminder_before_days": 7,
        "overdue_after_days": 7,
    },
    {
        "item_name": "Deworming",
        "category": "essential",
        "species": "cat",
        "recurrence_days": 90,
        "medicine_dependent": True,
        "reminder_before_days": 7,
        "overdue_after_days": 7,
    },
    # --- Tick/Flea Prevention ---
    # Essential for both dogs and cats. Monthly (30 days).
    # Medicine-dependent — specific product matters.
    # Reminder 5 days before, overdue after 3 days.
    {
        "item_name": "Tick/Flea",
        "category": "essential",
        "species": "dog",
        "recurrence_days": 30,
        "medicine_dependent": True,
        "reminder_before_days": 5,
        "overdue_after_days": 3,
    },
    {
        "item_name": "Tick/Flea",
        "category": "essential",
        "species": "cat",
        "recurrence_days": 30,
        "medicine_dependent": True,
        "reminder_before_days": 5,
        "overdue_after_days": 3,
    },
    # --- Annual Checkup ---
    # Complementary for both dogs and cats. Yearly (365 days).
    # Reminder 30 days before, overdue after 14 days.
    {
        "item_name": "Annual Checkup",
        "category": "complete",
        "species": "dog",
        "recurrence_days": 365,
        "medicine_dependent": False,
        "reminder_before_days": 30,
        "overdue_after_days": 14,
    },
    {
        "item_name": "Annual Checkup",
        "category": "complete",
        "species": "cat",
        "recurrence_days": 365,
        "medicine_dependent": False,
        "reminder_before_days": 30,
        "overdue_after_days": 14,
    },
    # --- Preventive Blood Test ---
    # Complementary for both dogs and cats. Yearly (365 days).
    # Reminder 30 days before, overdue after 14 days.
    {
        "item_name": "Preventive Blood Test",
        "category": "complete",
        "species": "dog",
        "recurrence_days": 365,
        "medicine_dependent": False,
        "reminder_before_days": 30,
        "overdue_after_days": 14,
    },
    {
        "item_name": "Preventive Blood Test",
        "category": "complete",
        "species": "cat",
        "recurrence_days": 365,
        "medicine_dependent": False,
        "reminder_before_days": 30,
        "overdue_after_days": 14,
    },
    # --- Dental Check ---
    # Complementary for both dogs and cats. Yearly (365 days).
    # Reminder 30 days before, overdue after 14 days.
    {
        "item_name": "Dental Check",
        "category": "complete",
        "species": "dog",
        "recurrence_days": 365,
        "medicine_dependent": False,
        "reminder_before_days": 30,
        "overdue_after_days": 14,
    },
    {
        "item_name": "Dental Check",
        "category": "complete",
        "species": "cat",
        "recurrence_days": 365,
        "medicine_dependent": False,
        "reminder_before_days": 30,
        "overdue_after_days": 14,
    },
]


def seed_preventive_master(db: Session) -> int:
    """
    Seed the preventive_master table with frozen health items.

    This function is idempotent — it only inserts if the table is empty.
    If any rows already exist, it skips seeding entirely and logs a message.

    The 8 items expand to 14 rows because species='both' items are
    stored as separate 'dog' and 'cat' rows to match the
    UNIQUE(item_name, species) constraint.

    Args:
        db: SQLAlchemy database session.

    Returns:
        Number of rows inserted (0 if table was already populated).
    """
    # Check if table already has data — only seed into empty table.
    # This prevents duplicate inserts on re-runs or redeployments.
    existing_count = db.query(PreventiveMaster).count()

    if existing_count > 0:
        logger.info(
            "Preventive master table already seeded (%d rows). Skipping.",
            existing_count,
        )
        return 0

    # Insert all seed rows.
    inserted = 0
    for item_data in SEED_DATA:
        row = PreventiveMaster(
            item_name=item_data["item_name"],
            category=item_data["category"],
            species=item_data["species"],
            recurrence_days=item_data["recurrence_days"],
            medicine_dependent=item_data["medicine_dependent"],
            reminder_before_days=item_data["reminder_before_days"],
            overdue_after_days=item_data["overdue_after_days"],
        )
        db.add(row)
        inserted += 1

    db.commit()
    logger.info("Preventive master table seeded with %d rows.", inserted)

    return inserted
