"""
PetCircle — Birthday Reminder Service

Handles creation and management of birthday reminders for pets.
Integrates with the preventive record system to track annual birthday events.

Key functions:
    - create_birthday_record: Creates initial birthday preventive record if DOB is provided
    - calculate_next_birthday: Calculates next birthday date from pet DOB
    - handle_birthday_celebration: Special handling for birthday reminders
"""

import logging
from datetime import date as DateType, datetime
from sqlalchemy.orm import Session
from app.models.pet import Pet
from app.models.preventive_record import PreventiveRecord
from app.models.preventive_master import PreventiveMaster
from app.utils.date_utils import get_today_ist

logger = logging.getLogger(__name__)


def calculate_next_birthday(dob: DateType) -> DateType:
    """
    Calculate the next birthday date from a given date of birth.

    This function takes a pet's DOB and calculates the upcoming birthday,
    accounting for whether the pet's birthday has already passed this year.

    Args:
        dob: The pet's date of birth.

    Returns:
        The date of the next birthday (this year or next year).
    """
    today = get_today_ist()

    # Extract month and day from DOB
    birthday_this_year = DateType(today.year, dob.month, dob.day)

    # If birthday hasn't occurred yet this year, return this year's date
    if birthday_this_year >= today:
        return birthday_this_year

    # Otherwise, return next year's birthday
    return DateType(today.year + 1, dob.month, dob.day)


def create_birthday_record(db: Session, pet: Pet) -> PreventiveRecord | None:
    """
    Create an initial birthday preventive record for a pet if DOB is provided.

    This function is called during pet onboarding. If the pet has a DOB,
    it creates a preventive record for the Birthday Celebration item with
    the next birthday date set as the last_done_date (so next_due_date
    will be calculated relative to it).

    Args:
        db: SQLAlchemy database session.
        pet: The Pet model instance (with dob already scalar value in memory).

    Returns:
        The created PreventiveRecord if successful, None if DOB not provided.
    """
    # Only create if pet has a DOB
    # Since pet is already loaded in memory, dob is a scalar value, not a Column
    if pet.dob is None:
        logger.info(
            "Skipping birthday record for pet_id=%s: no DOB provided",
            str(pet.id),
        )
        return None

    # Find the Birthday Celebration item for this species
    birthday_master = (
        db.query(PreventiveMaster)
        .filter(
            PreventiveMaster.item_name == "Birthday Celebration",
            PreventiveMaster.species == pet.species,
        )
        .first()
    )

    if not birthday_master:
        logger.warning(
            "Birthday Celebration master not found for species=%s. "
            "Ensure preventive master is seeded.",
            pet.species,
        )
        return None

    # Calculate the next birthday
    # Type cast: pet.dob is Column[date] in type hints but scalar date at runtime
    dob = pet.dob  # type: ignore
    next_birthday = calculate_next_birthday(dob)  # type: ignore
    today = get_today_ist()

    # For the birthday record, set:
    # - last_done_date: previous birthday (one year before next birthday)
    # - next_due_date: the upcoming birthday
    previous_birthday = DateType(next_birthday.year - 1, dob.month, dob.day)

    try:
        record = PreventiveRecord(
            pet_id=pet.id,
            preventive_master_id=birthday_master.id,
            last_done_date=previous_birthday,
            next_due_date=next_birthday,
            status="upcoming" if next_birthday <= today else "up_to_date",
        )
        db.add(record)
        db.flush()

        logger.info(
            "Birthday record created for pet_id=%s: "
            "dob=%s, next_birthday=%s, status=%s",
            str(pet.id),
            str(dob),
            str(next_birthday),
            record.status,
        )

        return record

    except Exception as e:
        logger.error(
            "Failed to create birthday record for pet_id=%s: %s",
            str(pet.id),
            str(e),
        )
        return None


async def send_birthday_message(
    db: Session,
    to_number: str,
    pet_name: str,
    birthday_date: str,
) -> dict | None:
    """
    Send a special birthday celebration template message.

    Different from regular reminders, birthday messages are celebratory
    and may include emojis or special formatting.

    Args:
        db: SQLAlchemy database session (for logging).
        to_number: Recipient's WhatsApp phone number.
        pet_name: Name of the pet celebrating birthday.
        birthday_date: Birthday date as string (formatted for user).

    Returns:
        API response dict on success, None on failure.
    """
    from app.services.whatsapp_sender import send_template_message
    from app.config import settings

    # Send the birthday template message with parameters.
    result = await send_template_message(
        db=db,
        to_number=to_number,
        template_name=settings.WHATSAPP_TEMPLATE_BIRTHDAY,
        parameters=[pet_name, birthday_date],
    )

    if result:
        logger.info(
            "Birthday template sent to %s for pet=%s on %s",
            to_number,
            pet_name,
            birthday_date,
        )
    else:
        logger.warning(
            "Birthday template failed for %s (pet=%s)",
            to_number,
            pet_name,
        )

    return result
