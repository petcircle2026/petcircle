"""
PetCircle — Order Service

Handles the WhatsApp order conversation flow:
    1. User types "order" → show category buttons
    2. User taps category → create draft order, ask for items
    3. User types items → save items, auto-select pet or ask
    4. User selects pet (if 2+) → show confirmation
    5. User taps confirm/cancel → finalize or abort

State is tracked via user.order_state and user.active_order_id.
"""

import logging
from sqlalchemy.orm import Session
from app.config import settings
from app.core.encryption import decrypt_field
from app.core.log_sanitizer import mask_phone
from app.core.constants import (
    ORDER_CAT_MEDICINES,
    ORDER_CAT_FOOD,
    ORDER_CAT_SUPPLEMENTS,
    ORDER_CONFIRM,
    ORDER_CANCEL,
    ORDER_CATEGORY_MAP,
    ORDER_CATEGORY_LABELS,
)
from app.models.order import Order
from app.models.pet import Pet
from app.services.whatsapp_sender import send_text_message, send_interactive_buttons

logger = logging.getLogger(__name__)


async def start_order_flow(db: Session, user) -> None:
    """
    Begin the order flow by sending category selection buttons.

    Sets user.order_state to 'awaiting_order_category' so the router
    knows to intercept the next button press as a category selection.
    """
    from_number = _get_mobile(user)

    # Check if user has any active (non-deleted) pets for personalization.
    pets = _get_active_pets(db, user)
    if pets and len(pets) == 1:
        body = f"What would you like to order for *{pets[0].name}*?"
    elif pets and len(pets) > 1:
        pet_names = ", ".join(p.name for p in pets)
        body = f"What would you like to order? (Pets: {pet_names})"
    else:
        body = "What would you like to order?"

    buttons = [
        {"id": ORDER_CAT_MEDICINES, "title": "Medicines"},
        {"id": ORDER_CAT_FOOD, "title": "Food & Nutrition"},
        {"id": ORDER_CAT_SUPPLEMENTS, "title": "Supplements"},
    ]

    user.order_state = "awaiting_order_category"
    db.commit()

    await send_interactive_buttons(db, from_number, body, buttons)
    logger.info("Order flow started for user %s", mask_phone(from_number))


async def handle_order_category(db: Session, user, payload: str) -> None:
    """
    Handle category button selection — create a draft order and ask for items.

    Args:
        payload: Button payload ID (ORDER_CAT_MEDICINES, etc.)
    """
    from_number = _get_mobile(user)
    category = ORDER_CATEGORY_MAP.get(payload)

    if not category:
        logger.warning("Invalid order category payload '%s' from %s", payload, mask_phone(from_number))
        await send_text_message(db, from_number, "Please select a valid category.")
        return

    # Create draft order with category only (items not yet provided).
    order = Order(
        user_id=user.id,
        category=category,
        items_description="",  # Will be filled when user types items.
        status="pending",
    )
    db.add(order)
    db.flush()  # Get the order ID before committing.

    user.active_order_id = order.id
    user.order_state = "awaiting_order_items"
    db.commit()

    label = ORDER_CATEGORY_LABELS.get(category, category)
    await send_text_message(
        db, from_number,
        f"*{label}* — got it!\n\n"
        f"Please type the item names and quantities you need.\n"
        f"Example: _Nexgard 3 tablets, Drontal 1 tablet_",
    )
    logger.info("Order category '%s' selected by %s", category, mask_phone(from_number))


async def handle_order_items(db: Session, user, text: str) -> None:
    """
    Handle items text — save to draft order, then route to pet selection or confirmation.

    Auto-selects pet if user has exactly 1 pet.
    Asks for pet selection if user has 2+ pets.
    Skips pet selection if user has 0 pets.
    """
    from_number = _get_mobile(user)
    order = _get_active_order(db, user)

    if not order:
        # Draft order not found — abort flow gracefully.
        await _abort_stale_flow(db, user, from_number)
        return

    # Save items description to the draft order.
    order.items_description = text.strip()[:2000]
    db.commit()

    pets = _get_active_pets(db, user)

    if len(pets) == 0:
        # No pets — skip pet selection, show confirmation without pet.
        await _show_order_confirmation(db, user, order, pet=None)
    elif len(pets) == 1:
        # Auto-select the only pet.
        order.pet_id = pets[0].id
        db.commit()
        await _show_order_confirmation(db, user, order, pet=pets[0])
    else:
        # Multiple pets — ask user to choose.
        user.order_state = "awaiting_order_pet"
        db.commit()
        pet_list = "\n".join(f"{i+1}. {p.name}" for i, p in enumerate(pets))
        await send_text_message(
            db, from_number,
            f"Which pet is this order for? Reply with the name or number:\n{pet_list}",
        )


async def handle_order_pet_selection(db: Session, user, text: str) -> None:
    """
    Handle pet name/number selection for multi-pet users.

    Matches by exact name (case-insensitive) or by list position number.
    """
    from_number = _get_mobile(user)
    order = _get_active_order(db, user)

    if not order:
        await _abort_stale_flow(db, user, from_number)
        return

    pets = _get_active_pets(db, user)
    text_lower = text.strip().lower()

    # Try to match by number first (e.g., "1", "2").
    matched_pet = None
    try:
        idx = int(text_lower) - 1
        if 0 <= idx < len(pets):
            matched_pet = pets[idx]
    except ValueError:
        pass

    # Try to match by name (case-insensitive).
    if not matched_pet:
        for p in pets:
            if p.name.lower() == text_lower:
                matched_pet = p
                break

    if not matched_pet:
        pet_list = "\n".join(f"{i+1}. {p.name}" for i, p in enumerate(pets))
        await send_text_message(
            db, from_number,
            f"I didn't recognize that pet name. Please reply with the name or number:\n{pet_list}",
        )
        return

    order.pet_id = matched_pet.id
    db.commit()
    await _show_order_confirmation(db, user, order, pet=matched_pet)


async def handle_order_confirmation(db: Session, user, payload: str) -> None:
    """
    Handle confirm/cancel button press on the order summary.

    On confirm: finalize the order, notify admin via WhatsApp, clear flow state.
    On cancel: delete draft order, clear flow state.
    """
    from_number = _get_mobile(user)
    order = _get_active_order(db, user)

    if not order:
        await _abort_stale_flow(db, user, from_number)
        return

    if payload == ORDER_CONFIRM:
        # Finalize the order — keep status as 'pending' for admin to process.
        order.status = "pending"
        _clear_order_state(db, user)

        pet = db.query(Pet).filter(Pet.id == order.pet_id).first() if order.pet_id else None

        await send_text_message(
            db, from_number,
            "Your order has been received! Our team will call you shortly to process it.",
        )

        # Notify admin via WhatsApp (if configured).
        await _notify_admin_whatsapp(db, order, user, pet)

        logger.info("Order confirmed: order_id=%s, user=%s", str(order.id), mask_phone(from_number))

    elif payload == ORDER_CANCEL:
        await cancel_order_flow(db, user)

    else:
        logger.warning("Unknown order confirmation payload '%s' from %s", payload, mask_phone(from_number))


async def cancel_order_flow(db: Session, user) -> None:
    """Cancel the active order flow — delete draft order, clear state, notify user."""
    from_number = _get_mobile(user)
    order = _get_active_order(db, user)

    if order:
        # Delete the draft order since it was never confirmed.
        db.delete(order)

    _clear_order_state(db, user)

    await send_text_message(db, from_number, "Order cancelled. Let me know if you need anything else!")
    logger.info("Order flow cancelled by %s", mask_phone(from_number))


# --- Private Helpers ---


async def _show_order_confirmation(db: Session, user, order: Order, pet) -> None:
    """Send order summary with Confirm/Cancel buttons."""
    from_number = _get_mobile(user)
    label = ORDER_CATEGORY_LABELS.get(order.category, order.category)

    pet_line = f"Pet: *{pet.name}*\n" if pet else ""
    body = (
        f"Here's your order summary:\n\n"
        f"{pet_line}"
        f"Category: *{label}*\n"
        f"Items: {order.items_description}\n\n"
        f"Would you like to confirm this order?"
    )

    buttons = [
        {"id": ORDER_CONFIRM, "title": "Confirm Order"},
        {"id": ORDER_CANCEL, "title": "Cancel"},
    ]

    # Move to awaiting confirmation state.
    user.order_state = "awaiting_order_confirm"
    db.commit()

    await send_interactive_buttons(db, from_number, body, buttons)


async def _notify_admin_whatsapp(db: Session, order: Order, user, pet) -> None:
    """
    Send a WhatsApp notification to the admin phone about a new order.

    Skips silently if ORDER_NOTIFICATION_PHONE is not configured.
    Never crashes — notification failure should not affect user experience.
    """
    admin_phone = settings.ORDER_NOTIFICATION_PHONE
    if not admin_phone:
        logger.info("ORDER_NOTIFICATION_PHONE not set — skipping WhatsApp admin notification.")
        return

    try:
        user_phone = decrypt_field(user.mobile_number)
        user_name = user.full_name or "Unknown"
        pet_name = pet.name if pet else "N/A"
        label = ORDER_CATEGORY_LABELS.get(order.category, order.category)

        msg = (
            f"New Order Received!\n\n"
            f"User: {user_name}\n"
            f"Phone: {user_phone}\n"
            f"Pet: {pet_name}\n"
            f"Category: {label}\n"
            f"Items: {order.items_description}\n\n"
            f"Please call the user to process this order."
        )

        await send_text_message(db, admin_phone, msg)
        logger.info("Admin notified about order %s", str(order.id))
    except Exception as e:
        # Never crash on notification failure — order is already confirmed.
        logger.error("Failed to notify admin about order %s: %s", str(order.id), str(e))


def _get_mobile(user) -> str:
    """Get decrypted mobile number from user."""
    return decrypt_field(user.mobile_number)


def _get_active_pets(db: Session, user) -> list:
    """Get all active (non-deleted) pets for a user, ordered by name."""
    return (
        db.query(Pet)
        .filter(Pet.user_id == user.id, Pet.is_deleted == False)
        .order_by(Pet.name)
        .all()
    )


def _get_active_order(db: Session, user) -> Order | None:
    """Get the user's active draft order by active_order_id."""
    if not user.active_order_id:
        return None
    return db.query(Order).filter(Order.id == user.active_order_id).first()


def _clear_order_state(db: Session, user) -> None:
    """Clear the order flow state from the user record."""
    user.order_state = None
    user.active_order_id = None
    db.commit()


async def _abort_stale_flow(db: Session, user, from_number: str) -> None:
    """Handle case where order state exists but draft order is missing."""
    _clear_order_state(db, user)
    await send_text_message(
        db, from_number,
        "Something went wrong with your order. Please type *order* to start again.",
    )
    logger.warning("Stale order flow cleared for %s", mask_phone(from_number))
