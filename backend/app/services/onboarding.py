"""
PetCircle Phase 1 — Onboarding Service

Handles the multi-step WhatsApp conversation for user registration
and pet profile creation. State is tracked via user.onboarding_state.

Conversation flow:
    1. New number → Create user row (awaiting_consent) → ask consent
    2. "yes" → consent_given=True, state=awaiting_name → ask name
    3. Name → store full_name, state=awaiting_pincode → ask pincode
    4. Pincode → store pincode, state=awaiting_pet_name → ask pet name
    5. Pet name → state=awaiting_species → ask dog or cat
    6. Species → create Pet, state=awaiting_breed → ask breed
    7. Breed or "skip" → state=awaiting_gender → ask gender
    8. Gender or "skip" → state=awaiting_dob → ask DOB
    9. DOB or "skip" → state=awaiting_weight → ask weight
   10. Weight or "skip" → state=awaiting_neutered → ask neutered
   11. Neutered or "skip" → seed preventive records, generate token,
       state=complete → send dashboard link

Rules:
    - Max 5 pets per user (from constants).
    - Consent must be recorded before any data is stored.
    - All dates parsed via date_utils.
    - Species restricted to 'dog' or 'cat'.
    - "skip" accepted for optional fields.
"""

import logging
import secrets
from datetime import datetime, timedelta
from uuid import UUID
from sqlalchemy.orm import Session
from app.models.user import User
from app.models.pet import Pet
from app.models.dashboard_token import DashboardToken
from app.models.preventive_master import PreventiveMaster
from app.models.preventive_record import PreventiveRecord
from app.core.constants import (
    MAX_PETS_PER_USER,
    MAX_PET_WEIGHT_KG,
    DASHBOARD_TOKEN_BYTES,
    DASHBOARD_TOKEN_EXPIRY_DAYS,
    GREETINGS,
)
from app.config import settings
from app.core.encryption import encrypt_field, decrypt_field, hash_field
from app.core.log_sanitizer import mask_phone
from app.utils.date_utils import parse_date, parse_date_with_ai
from app.utils.breed_normalizer import normalize_breed, normalize_breed_with_ai
from app.services.preventive_seeder import seed_preventive_master


logger = logging.getLogger(__name__)

# --- Colloquial input sets ---
# Accepted variations for yes/no across all onboarding steps.
_YES_INPUTS = frozenset({
    "yes", "y", "yeah", "yea", "yep", "yup", "ya", "yah",
    "sure", "ok", "okay", "agree", "alright", "aight",
    "absolutely", "definitely", "of course", "haan", "ha",
})
_NO_INPUTS = frozenset({
    "no", "n", "nah", "nope", "nay", "na", "not really",
    "disagree", "nahi",
})
# Accepted variations for skip across all onboarding steps.
_SKIP_INPUTS = frozenset({"skip", "s"})


def get_or_create_user(db: Session, mobile_number: str) -> tuple[User | None, bool]:
    """
    Look up an existing user by mobile number hash, or return None if new.

    Uses deterministic SHA-256 hash for lookups instead of querying
    the encrypted mobile_number column directly.

    Also checks for soft-deleted users with the same hash and includes
    them in the lookup — see notes on create_pending_user.

    Args:
        db: SQLAlchemy database session.
        mobile_number: WhatsApp phone number (plaintext from webhook).

    Returns:
        Tuple of (User or None, is_existing: bool).
    """
    mobile_h = hash_field(mobile_number)
    user = (
        db.query(User)
        .filter(User.mobile_hash == mobile_h, User.is_deleted == False)
        .first()
    )
    if user:
        return user, True
    return None, False


def create_pending_user(db: Session, mobile_number: str) -> User:
    """
    Create a new user record in awaiting_consent state.

    Handles race conditions: if two webhooks arrive simultaneously for
    the same new number, the second call re-checks for an existing user
    before inserting. If a duplicate IntegrityError occurs, falls back
    to returning the existing record.

    Also reactivates soft-deleted users (consent previously denied)
    instead of creating a duplicate row.

    Args:
        db: SQLAlchemy database session.
        mobile_number: WhatsApp phone number (plaintext).

    Returns:
        The created or existing User model instance.
    """
    mobile_h = hash_field(mobile_number)

    # --- Guard against duplicates ---
    # Re-check inside create to handle race conditions where two webhook
    # calls pass get_or_create_user simultaneously for a new number.
    existing = (
        db.query(User)
        .filter(User.mobile_hash == mobile_h)
        .first()
    )
    if existing:
        if existing.is_deleted:
            # Reactivate a previously soft-deleted user (consent denied earlier).
            existing.is_deleted = False
            existing.onboarding_state = "awaiting_consent"
            existing.consent_given = False
            db.commit()
            logger.info(
                "Reactivated soft-deleted user: id=%s, mobile=%s",
                str(existing.id), mask_phone(mobile_number),
            )
            return existing
        # Active user already exists — return it (race condition resolved).
        logger.info(
            "User already exists (race condition): id=%s, mobile=%s",
            str(existing.id), mask_phone(mobile_number),
        )
        return existing

    user = User(
        mobile_number=encrypt_field(mobile_number),
        mobile_hash=hash_field(mobile_number),
        mobile_display=mobile_number,
        full_name="_pending",
        onboarding_state="awaiting_consent",
        consent_given=False,
    )
    db.add(user)

    try:
        db.commit()
        db.refresh(user)
    except Exception as e:
        # IntegrityError from unique constraint — another request created it first.
        db.rollback()
        logger.warning("Duplicate user insert caught: %s", str(e))
        existing = (
            db.query(User)
            .filter(User.mobile_hash == mobile_h, User.is_deleted == False)
            .first()
        )
        if existing:
            return existing
        raise  # Re-raise if we still can't find the user.

    logger.info("Pending user created: id=%s, mobile=%s", str(user.id), mask_phone(mobile_number))
    return user


async def handle_onboarding_step(
    db: Session,
    user: User,
    text: str,
    send_fn,
    message_data: dict | None = None,
) -> None:
    """
    Process one step of the onboarding conversation.

    Routes to the correct handler based on user.onboarding_state.
    If the user sends a greeting mid-onboarding, shows progress summary
    and re-asks the current question instead of treating it as step input.

    Args:
        db: SQLAlchemy database session.
        user: The User model instance.
        text: The user's message text (stripped).
        send_fn: Async function to send WhatsApp text messages.
            Signature: send_fn(db, to_number, text) -> None
        message_data: Optional dict from webhook with profile_name etc.
    """
    state = user.onboarding_state or "awaiting_consent"
    # Prefer cached plaintext mobile from the current request (set by message_router).
    # Falls back to decrypting the stored encrypted mobile_number.
    mobile = getattr(user, "_plaintext_mobile", None) or decrypt_field(user.mobile_number)
    # Ensure all downstream step functions can access plaintext mobile.
    user._plaintext_mobile = mobile
    text_lower = text.lower().strip()

    # Detect greetings mid-onboarding — show progress summary and re-ask current question.
    if _is_greeting(text_lower):
        await _send_onboarding_resume(db, user, state, send_fn)
        return

    if state == "awaiting_consent":
        await _step_consent(db, user, text_lower, send_fn, message_data=message_data)

    elif state == "awaiting_name":
        await _step_name(db, user, text, send_fn, message_data=message_data)

    elif state == "awaiting_pincode":
        await _step_pincode(db, user, text, send_fn)

    elif state == "awaiting_pet_name":
        await _step_pet_name(db, user, text, send_fn)

    elif state == "awaiting_species":
        await _step_species(db, user, text_lower, send_fn)

    elif state == "awaiting_breed":
        await _step_breed(db, user, text, send_fn)

    elif state == "awaiting_gender":
        await _step_gender(db, user, text_lower, send_fn)

    elif state == "awaiting_dob":
        await _step_dob(db, user, text, send_fn)

    elif state == "awaiting_weight":
        await _step_weight(db, user, text, send_fn)

    elif state == "awaiting_neutered":
        await _step_neutered(db, user, text_lower, send_fn)

    else:
        # Unknown state — recover by resetting to consent step.
        logger.warning("Unknown onboarding state '%s' for user %s — resetting to awaiting_consent", state, mobile)
        user.onboarding_state = "awaiting_consent"
        db.commit()
        await send_fn(
            db, mobile,
            "Something went wrong with your setup. Let's start over.\n\n"
            "Reply *yes* to continue or *no* to opt out.",
        )


def _is_greeting(text_lower: str) -> bool:
    """Check if the message is a greeting rather than onboarding input."""
    return text_lower in GREETINGS


async def _send_onboarding_resume(db, user, state, send_fn):
    """
    Send a welcome-back message showing what has been filled so far,
    then re-ask the current onboarding question.

    Business rule: Until onboarding is complete, any greeting should
    show the welcome message, display progress, and prompt the next step.
    """
    mobile = user._plaintext_mobile

    # Build progress summary from data already collected.
    progress_lines = []
    if user.consent_given:
        progress_lines.append("Consent: Yes")
    if user.full_name and user.full_name != "_pending":
        progress_lines.append(f"Name: {user.full_name}")
    if user.pincode:
        progress_lines.append("Pincode: Provided")

    # Check if a pet is being onboarded.
    pet = _get_pending_pet(db, user.id)
    if pet:
        progress_lines.append(f"Pet name: {pet.name}")
        if pet.species and pet.species != "_pending":
            progress_lines.append(f"Species: {pet.species}")
        if pet.breed:
            progress_lines.append(f"Breed: {pet.breed}")
        if pet.gender:
            progress_lines.append(f"Gender: {pet.gender}")
        if pet.dob:
            progress_lines.append(f"DOB: {pet.dob.strftime('%d/%m/%Y')}")
        if pet.weight:
            progress_lines.append(f"Weight: {pet.weight} kg")
        if pet.neutered is not None:
            progress_lines.append(f"Neutered: {'Yes' if pet.neutered else 'No'}")

    # Compose welcome-back header.
    greeting = "Welcome back to *PetCircle* 🐾\n\nLet's continue setting up your profile."

    if progress_lines:
        greeting += "\n\nHere's what we have so far:\n" + "\n".join(f"  • {line}" for line in progress_lines)

    # Map state → next question prompt.
    next_question = _get_question_for_state(state, pet)

    await send_fn(db, mobile, f"{greeting}\n\n{next_question}")


def _get_question_for_state(state: str, pet=None) -> str:
    """Return the question prompt corresponding to the current onboarding state."""
    pet_name = pet.name if pet else "your pet"

    prompts = {
        "awaiting_consent": (
            "Before we begin, I need your consent to store your pet's health data.\n\n"
            "Reply *yes* to get started or *no* to opt out."
        ),
        "awaiting_name": "What is your *full name*?",
        "awaiting_pincode": "What is your *pincode*? (Type *skip* if you prefer not to share)",
        "awaiting_pet_name": "What is your *pet's name*?",
        "awaiting_species": f"Is *{pet_name}* a *dog* or a *cat*?",
        "awaiting_breed": f"What *breed* is {pet_name}? (Type *skip* if you're not sure)",
        "awaiting_gender": f"What is {pet_name}'s *gender*? (*male* or *female*, or *skip*)",
        "awaiting_dob": f"When was {pet_name} born? (or type *skip*)",
        "awaiting_weight": f"What is {pet_name}'s *weight* in kg? (e.g., 12.5, or *skip*)",
        "awaiting_neutered": f"Is {pet_name} *neutered/spayed*? (*yes*, *no*, or *skip*)",
    }
    return prompts.get(state, "Let's continue setting up your profile.")


async def _step_consent(db, user, text_lower, send_fn, message_data: dict | None = None):
    """Handle consent step."""
    if text_lower in _YES_INPUTS:
        user.consent_given = True
        user.onboarding_state = "awaiting_name"
        db.commit()

        # Pull WhatsApp profile name and offer it as default.
        profile_name = (message_data or {}).get("profile_name")
        if profile_name:
            # Store the profile name temporarily so _step_name can use it.
            user._wa_profile_name = profile_name
            await send_fn(
                db, user._plaintext_mobile,
                f"Thank you for your consent! Let's get you set up.\n\n"
                f"Your WhatsApp name is *{profile_name}*. "
                f"Should I use this as your name? Reply *yes* or enter a different name.",
            )
        else:
            await send_fn(
                db, user._plaintext_mobile,
                "Thank you for your consent! Let's get you set up.\n\n"
                "What is your *full name*?",
            )
    elif text_lower in _NO_INPUTS:
        await send_fn(
            db, user._plaintext_mobile,
            "No problem. Your data won't be stored. "
            "Send a message anytime if you change your mind.",
        )
        # Soft delete the pending user
        user.is_deleted = True
        db.commit()
    else:
        await send_fn(
            db, user._plaintext_mobile,
            "Please reply *yes* to consent and continue, or *no* to opt out.",
        )


async def _step_name(db, user, text, send_fn, message_data: dict | None = None):
    """Handle name collection. Accepts WhatsApp profile name via 'yes'/'y'."""
    text_lower = text.strip().lower()

    # If user confirms WhatsApp profile name with yes/y.
    wa_name = getattr(user, "_wa_profile_name", None)
    if not wa_name:
        # Try to get it from message_data.
        wa_name = (message_data or {}).get("profile_name")

    if text_lower in _YES_INPUTS and wa_name:
        user.full_name = wa_name.strip().title()
    else:
        if len(text) < 2 or len(text) > 120:
            await send_fn(db, user._plaintext_mobile, "Please enter a valid name (2-120 characters).")
            return
        user.full_name = text.strip().title()

    user.onboarding_state = "awaiting_pincode"
    db.commit()

    await send_fn(
        db, user._plaintext_mobile,
        f"Nice to meet you, {user.full_name}!\n\n"
        f"What is your *pincode*? (Type *skip* if you prefer not to share)",
    )


async def _step_pincode(db, user, text, send_fn):
    """Handle pincode collection."""
    text_stripped = text.strip()
    if text_stripped.lower() in _SKIP_INPUTS:
        user.onboarding_state = "awaiting_pet_name"
        db.commit()
    else:
        # Validate Indian pincode (6 digits)
        if text_stripped.isdigit() and len(text_stripped) == 6:
            # Encrypt pincode before storing — PII protection.
            user.pincode = encrypt_field(text_stripped)
            user.onboarding_state = "awaiting_pet_name"
            db.commit()
        else:
            await send_fn(
                db, user._plaintext_mobile,
                "Please enter a valid 6-digit Indian pincode, or type *skip*.",
            )
            return

    await send_fn(
        db, user._plaintext_mobile,
        "Now let's add your pet!\n\n"
        "What is your *pet's name*?",
    )


async def _step_pet_name(db, user, text, send_fn):
    """Handle pet name collection — store temporarily, ask species next."""
    # Title-case pet name for consistent display (zayn → Zayn).
    pet_name = text.strip().title()
    if len(pet_name) < 1 or len(pet_name) > 100:
        await send_fn(db, user._plaintext_mobile, "Please enter a valid pet name.")
        return

    # Check pet limit
    pet_count = (
        db.query(Pet)
        .filter(Pet.user_id == user.id, Pet.is_deleted == False)
        .count()
    )
    if pet_count >= MAX_PETS_PER_USER:
        await send_fn(
            db, user._plaintext_mobile,
            f"You already have {MAX_PETS_PER_USER} pets registered. That's the maximum!",
        )
        user.onboarding_state = "complete"
        db.commit()
        return

    # Create pet with placeholder species — will be updated in next step.
    # Store name now so we don't lose it between messages.
    pet = Pet(
        user_id=user.id,
        name=pet_name,
        species="_pending",
    )
    db.add(pet)
    db.commit()

    user.onboarding_state = "awaiting_species"
    db.commit()

    await send_fn(
        db, user._plaintext_mobile,
        f"Great name! Is *{pet_name}* a *dog* or a *cat*?",
    )


async def _step_species(db, user, text_lower, send_fn):
    """Handle species selection. Accepts 'd'/'c' shortcuts."""
    # Map shortcuts to full species names.
    species_map = {"d": "dog", "dog": "dog", "c": "cat", "cat": "cat"}
    species = species_map.get(text_lower)

    if not species:
        await send_fn(
            db, user._plaintext_mobile,
            "Please reply *dog* or *cat*.",
        )
        return

    # Update the pending pet
    pet = _get_pending_pet(db, user.id)
    if not pet:
        await send_fn(db, user._plaintext_mobile, "Something went wrong. Please send your pet's name again.")
        user.onboarding_state = "awaiting_pet_name"
        db.commit()
        return

    pet.species = species
    user.onboarding_state = "awaiting_breed"
    db.commit()

    await send_fn(
        db, user._plaintext_mobile,
        f"What *breed* is {pet.name}? (Type *skip* if you're not sure)",
    )


async def _step_breed(db, user, text, send_fn):
    """Handle breed collection. Uses AI fallback if local normalizer fails."""
    pet = _get_pending_pet(db, user.id)
    if not pet:
        user.onboarding_state = "awaiting_pet_name"
        db.commit()
        await send_fn(db, user._plaintext_mobile, "Something went wrong. Please send your pet's name again.")
        return

    if text.strip().lower() not in _SKIP_INPUTS:
        # Try local normalizer first.
        normalized = normalize_breed(text.strip(), species=pet.species)

        # If normalizer just title-cased it (no match found), try AI.
        if normalized == text.strip().title():
            try:
                normalized = await normalize_breed_with_ai(text.strip(), species=pet.species)
            except Exception:
                pass  # Keep the title-cased version if AI fails.

        pet.breed = normalized

    user.onboarding_state = "awaiting_gender"
    db.commit()

    breed_confirm = f" {pet.breed}" if pet.breed else ""
    await send_fn(
        db, user._plaintext_mobile,
        f"Got it{breed_confirm}! What is {pet.name}'s *gender*? (*male* or *female*, or *skip*)",
    )


async def _step_gender(db, user, text_lower, send_fn):
    """Handle gender collection. Accepts 'm'/'f' shortcuts."""
    pet = _get_pending_pet(db, user.id)
    if not pet:
        user.onboarding_state = "awaiting_pet_name"
        db.commit()
        await send_fn(db, user._plaintext_mobile, "Something went wrong. Please send your pet's name again.")
        return

    # Map shortcuts to full gender values.
    gender_map = {"m": "male", "male": "male", "f": "female", "female": "female"}
    gender = gender_map.get(text_lower)

    if gender:
        pet.gender = gender
    elif text_lower not in _SKIP_INPUTS:
        await send_fn(db, user._plaintext_mobile, "Please reply *male*, *female*, or *skip*.")
        return

    user.onboarding_state = "awaiting_dob"
    db.commit()

    await send_fn(
        db, user._plaintext_mobile,
        f"When was {pet.name} born? (or type *skip*)",
    )


async def _step_dob(db, user, text, send_fn):
    """Handle date of birth collection. Accepts all formats, AI fallback."""
    pet = _get_pending_pet(db, user.id)
    if not pet:
        user.onboarding_state = "awaiting_pet_name"
        db.commit()
        await send_fn(db, user._plaintext_mobile, "Something went wrong. Please send your pet's name again.")
        return

    if text.strip().lower() not in _SKIP_INPUTS:
        dob = None

        # Try standard format parsing first.
        try:
            dob = parse_date(text.strip())
        except ValueError:
            pass

        # If standard parsing failed, try AI.
        if dob is None:
            try:
                dob = await parse_date_with_ai(text.strip())
            except ValueError:
                await send_fn(
                    db, user._plaintext_mobile,
                    "I couldn't understand that date. Try something like 25/03/2024, "
                    "March 2024, or 2022. Type *skip* to skip.",
                )
                return

        # DOB cannot be in the future.
        from datetime import date as date_type
        if dob > date_type.today():
            await send_fn(
                db, user._plaintext_mobile,
                "Date of birth cannot be in the future. Please try again.",
            )
            return

        pet.dob = dob

    user.onboarding_state = "awaiting_weight"
    db.commit()

    await send_fn(
        db, user._plaintext_mobile,
        f"What is {pet.name}'s *weight* in kg? (e.g., 12.5, or *skip*)",
    )


async def _step_weight(db, user, text, send_fn):
    """Handle weight collection. Max 100kg, breed-based range check."""
    pet = _get_pending_pet(db, user.id)
    if not pet:
        user.onboarding_state = "awaiting_pet_name"
        db.commit()
        await send_fn(db, user._plaintext_mobile, "Something went wrong. Please send your pet's name again.")
        return

    if text.strip().lower() not in _SKIP_INPUTS:
        try:
            weight = float(text.strip())
            if weight <= 0:
                raise ValueError("must be positive")
            if weight > MAX_PET_WEIGHT_KG:
                await send_fn(
                    db, user._plaintext_mobile,
                    f"That seems too heavy. The maximum allowed weight is {int(MAX_PET_WEIGHT_KG)} kg. "
                    f"Please enter a valid weight, or type *skip*.",
                )
                return
            # Breed-based weight range check.
            breed_range = _get_breed_weight_range(pet.breed, pet.species)
            if breed_range:
                min_w, max_w = breed_range
                if weight < min_w or weight > max_w:
                    await send_fn(
                        db, user._plaintext_mobile,
                        f"A typical {pet.breed} weighs between {min_w}-{max_w} kg. "
                        f"You entered {weight} kg. If that's correct, send the weight again to confirm.",
                    )
                    # Allow re-entry — don't block. But flag for next attempt.
                    # Store the "warned" flag so next time we accept it.
                    if not getattr(user, "_weight_warned", False):
                        user._weight_warned = True
                        return
            pet.weight = weight
        except ValueError:
            await send_fn(
                db, user._plaintext_mobile,
                f"Please enter a valid weight in kg (e.g., 12.5). Max {int(MAX_PET_WEIGHT_KG)} kg. Or type *skip*.",
            )
            return

    user.onboarding_state = "awaiting_neutered"
    db.commit()

    await send_fn(
        db, user._plaintext_mobile,
        f"Is {pet.name} *neutered/spayed*? (*yes*, *no*, or *skip*)",
    )


async def _step_neutered(db, user, text_lower, send_fn):
    """Handle neutered status and complete onboarding."""
    pet = _get_pending_pet(db, user.id)
    if not pet:
        user.onboarding_state = "awaiting_pet_name"
        db.commit()
        await send_fn(db, user._plaintext_mobile, "Something went wrong. Please send your pet's name again.")
        return

    if text_lower in _YES_INPUTS:
        pet.neutered = True
    elif text_lower in _NO_INPUTS:
        pet.neutered = False
    elif text_lower not in _SKIP_INPUTS:
        await send_fn(db, user._plaintext_mobile, "Please reply *yes*, *no*, or *skip*.")
        return

    db.commit()

    # --- Complete onboarding ---
    await _complete_pet_onboarding(db, user, pet, send_fn)


async def _complete_pet_onboarding(db, user, pet, send_fn):
    """
    Finalize pet onboarding: seed records, generate token, send dashboard link.

    Each step is wrapped independently so a failure in one (e.g., token
    generation) doesn't block the others. The user always receives a
    message explaining what happened.
    """
    mobile = user._plaintext_mobile

    # --- Step 1: Seed preventive records ---
    record_count = 0
    try:
        record_count = seed_preventive_records_for_pet(db, pet)
    except Exception as e:
        logger.error(
            "Preventive seeding failed for pet %s: %s",
            str(pet.id), str(e), exc_info=True,
        )
        try:
            db.rollback()
        except Exception:
            pass

    if record_count == 0:
        logger.warning(
            "Zero preventive records created for pet %s (species=%s)",
            str(pet.id), pet.species,
        )

    # --- Step 2: Generate dashboard token ---
    token = None
    try:
        token = generate_dashboard_token(db, pet.id)
    except Exception as e:
        logger.error(
            "Dashboard token generation failed for pet %s: %s",
            str(pet.id), str(e), exc_info=True,
        )
        try:
            db.rollback()
        except Exception:
            pass

    # --- Step 3: Mark onboarding complete (must succeed) ---
    try:
        user.onboarding_state = "complete"
        db.commit()
    except Exception as e:
        logger.error("Failed to mark onboarding complete: %s", str(e), exc_info=True)
        try:
            db.rollback()
        except Exception:
            pass
        # Even if commit fails, don't leave user stuck — try to inform them.
        try:
            await send_fn(
                db, mobile,
                f"{pet.name}'s profile was created but we hit a temporary issue. "
                f"Please send *hi* to retry.",
            )
        except Exception:
            pass
        return

    logger.info(
        "Onboarding complete: user_id=%s, pet=%s (%s), records=%d, token=%s",
        str(user.id), pet.name, pet.species, record_count,
        "generated" if token else "FAILED",
    )

    # --- Step 4: Send completion message ---
    msg = f"All set! {pet.name}'s profile is ready.\n\n"

    if record_count > 0:
        msg += f"Preventive health items: {record_count} items are now being tracked.\n\n"
    else:
        msg += (
            "We couldn't load the preventive health items right now. "
            "They will be set up automatically — no action needed.\n\n"
        )

    if token:
        msg += (
            f"View *{pet.name}'s Dashboard* here:\n"
            f"{settings.FRONTEND_URL}/dashboard/{token}\n\n"
        )
    else:
        msg += (
            "Dashboard link couldn't be generated right now. "
            "Send *dashboard* anytime to get your link.\n\n"
        )

    msg += (
        f"You can upload medical records (photos, PDFs) anytime to update "
        f"{pet.name}'s health data.\n\n"
        f"Type *add pet* to add another pet, or ask any question about "
        f"{pet.name}'s health!"
    )

    await send_fn(db, mobile, msg)


def _get_breed_weight_range(breed: str | None, species: str | None) -> tuple[float, float] | None:
    """
    Return typical (min, max) weight range in kg for a breed.

    Used to warn users if their input seems off. Not exhaustive —
    returns None for unknown breeds (no warning given).
    """
    if not breed:
        return None

    # Common breed weight ranges (kg). Covers popular breeds in India.
    _BREED_WEIGHTS: dict[str, tuple[float, float]] = {
        # Dogs
        "Labrador Retriever": (25, 36),
        "Golden Retriever": (25, 34),
        "German Shepherd": (22, 40),
        "Siberian Husky": (16, 27),
        "Rottweiler": (35, 60),
        "Doberman Pinscher": (27, 45),
        "Dachshund": (5, 15),
        "Shih Tzu": (4, 7),
        "Pomeranian": (1.5, 3.5),
        "Chihuahua": (1, 3),
        "Yorkshire Terrier": (1.5, 3.2),
        "Maltese": (1.5, 4),
        "Border Collie": (12, 20),
        "Jack Russell Terrier": (5, 8),
        "Cane Corso": (40, 50),
        "American Pit Bull Terrier": (14, 27),
        "Indian Pariah Dog": (15, 30),
        "Beagle": (9, 11),
        "Pug": (6, 8),
        "Cocker Spaniel": (12, 16),
        "Boxer": (25, 32),
        "Great Dane": (45, 90),
        "Saint Bernard": (54, 82),
        # Cats
        "Persian": (3, 7),
        "Siamese": (3, 5),
        "Maine Coon": (5, 11),
        "Ragdoll": (4, 9),
        "British Shorthair": (4, 8),
        "Bengal": (4, 7),
        "Sphynx": (3, 5),
        "Indian Domestic Cat": (3, 6),
        "Domestic Shorthair": (3, 6),
    }

    return _BREED_WEIGHTS.get(breed)


def _get_pending_pet(db: Session, user_id: UUID) -> Pet | None:
    """Get the most recently created pet for a user (the one being onboarded)."""
    return (
        db.query(Pet)
        .filter(Pet.user_id == user_id, Pet.is_deleted == False)
        .order_by(Pet.created_at.desc())
        .first()
    )


def generate_dashboard_token(db: Session, pet_id: UUID) -> str:
    """
    Generate a secure random dashboard token for a pet.

    Token is 128-bit (16 bytes), rendered as a 32-char hex string.
    Expires after DASHBOARD_TOKEN_EXPIRY_DAYS (30 days by default).

    Args:
        db: SQLAlchemy database session.
        pet_id: UUID of the pet.

    Returns:
        The generated hex token string.
    """
    token = secrets.token_hex(DASHBOARD_TOKEN_BYTES)

    dashboard_token = DashboardToken(
        pet_id=pet_id,
        token=token,
        revoked=False,
        expires_at=datetime.utcnow() + timedelta(days=DASHBOARD_TOKEN_EXPIRY_DAYS),
    )
    db.add(dashboard_token)
    db.commit()

    logger.info("Dashboard token generated for pet_id=%s", str(pet_id))
    return token


def refresh_dashboard_token(db: Session, pet_id: UUID) -> str:
    """
    Revoke the existing token and generate a new one with fresh expiry.

    Used when a user's token has expired or been revoked and they
    request a new dashboard link via WhatsApp.

    Args:
        db: SQLAlchemy database session.
        pet_id: UUID of the pet.

    Returns:
        The newly generated hex token string.
    """
    # Batch-revoke all existing active tokens for this pet.
    revoked_count = (
        db.query(DashboardToken)
        .filter(DashboardToken.pet_id == pet_id, DashboardToken.revoked == False)
        .update({"revoked": True})
    )

    db.flush()

    logger.info("Revoked %d old token(s) for pet_id=%s", revoked_count, str(pet_id))
    return generate_dashboard_token(db, pet_id)


def seed_preventive_records_for_pet(db: Session, pet: Pet) -> int:
    """
    Create initial preventive records for a newly onboarded pet.

    Args:
        db: SQLAlchemy database session.
        pet: The Pet model instance.

    Returns:
        Count of preventive records created.
    """
    seed_preventive_master(db)

    masters = (
        db.query(PreventiveMaster)
        .filter(PreventiveMaster.species.in_([pet.species, "both"]))
        .all()
    )

    count = 0
    for master in masters:
        try:
            # Use a savepoint so individual failures only roll back this insert,
            # not the entire transaction (which would lose previously flushed records).
            nested = db.begin_nested()
            record = PreventiveRecord(
                pet_id=pet.id,
                preventive_master_id=master.id,
                status="upcoming",
            )
            db.add(record)
            db.flush()
            nested.commit()
            count += 1
        except Exception as e:
            nested.rollback()
            logger.warning(
                "Failed to create preventive record for pet=%s, item=%s: %s",
                str(pet.id), master.item_name, str(e),
            )

    db.commit()

    logger.info(
        "Seeded %d preventive records for pet_id=%s (species=%s)",
        count, str(pet.id), pet.species,
    )
    return count
