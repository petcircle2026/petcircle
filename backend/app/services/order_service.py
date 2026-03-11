"""
PetCircle — Order Service

Handles the WhatsApp order conversation flow:
    1. User types "order" → show category buttons
    2. User taps category → get AI recommendations (if pet available)
    3. User selects items from recommendations or types custom items
    4. User selects pet (if 2+ pets) → show confirmation
    5. User taps confirm/cancel → finalize or abort
    6. Preferences are recorded for future personalization

Flow states:
    - awaiting_order_category: after user types "order"
    - awaiting_reco_sel: after user selects category (if recommendations available)
    - awaiting_order_items: if no recommendations or after cancel recommendation
    - awaiting_order_pet: multi-pet selection
    - awaiting_order_confirm: confirmation

State is tracked via user.order_state and user.active_order_id.
"""

import logging
from uuid import UUID
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
    ORDER_FULFILL_YES_PREFIX,
    ORDER_FULFILL_NO_PREFIX,
)
from app.models.order import Order
from app.models.pet import Pet
from app.services.whatsapp_sender import send_text_message, send_interactive_buttons
from app.services.recommendation_service import (
    get_or_generate_recommendations,
    get_pet_top_preferences,
    record_preference,
)

logger = logging.getLogger(__name__)


async def start_order_flow(db: Session, user) -> None:
    """
    Begin the order flow by sending category selection buttons.

    Sets user.order_state to 'awaiting_order_category' so the router
    knows to intercept the next button press as a category selection.
    """
    from_number = _get_mobile(user)

    # Clean up any abandoned draft order from a previous incomplete flow.
    # Draft orders have empty items_description — they were created when the
    # user selected a category but never confirmed.
    if user.active_order_id:
        old_order = db.query(Order).filter(Order.id == user.active_order_id).first()
        if old_order and not old_order.items_description:
            db.delete(old_order)
            logger.info("Cleaned up abandoned draft order %s", str(old_order.id))
        _clear_order_state(db, user)

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
    Handle category button selection — create a draft order and get recommendations.

    If user has 1 active pet, try to generate recommendations for that pet.
    If recommendations found, show them as a numbered list.
    Otherwise, fall back to asking for free-text items.

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
        items_description="",  # Will be filled when user selects items.
        status="pending",
    )
    db.add(order)
    db.flush()  # Get the order ID before committing.

    user.active_order_id = order.id
    label = ORDER_CATEGORY_LABELS.get(category, category)

    # Try to get recommendations based on pet profile.
    # For multi-pet users, ask pet first to personalize recommendations.
    pets = _get_active_pets(db, user)
    recommendations = []

    if len(pets) > 1:
        user.order_state = "awaiting_pet_reco"
        db.commit()
        pet_list = "\n".join(f"{i+1}. {p.name}" for i, p in enumerate(pets))
        await send_text_message(
            db,
            from_number,
            f"Which pet is this for? Reply with the name or number:\n{pet_list}",
        )
        return

    if len(pets) == 1:
        try:
            pet = pets[0]
            recommendations = await _get_numbered_suggestions(
                db,
                pet,
                category,
                increment_on_hit=True,
            )

            if recommendations:
                # Store pet_id for preference tracking later
                order.pet_id = pet.id
                db.commit()
                user.order_state = "awaiting_reco_sel"
                db.commit()
                await _send_recommendation_list(db, from_number, label, pet.name, recommendations)
                logger.info(
                    "Order category '%s' selected with %d recommendations for %s",
                    category, len(recommendations), mask_phone(from_number)
                )
                return
        
        except Exception as e:
            logger.warning(f"Failed to get recommendations: {e}")
            recommendations = []
    
    # No recommendations available or user has multiple pets — fall back to custom items
    user.order_state = "awaiting_order_items"
    db.commit()

    await send_text_message(
        db, from_number,
        f"*{label}* — got it!\n\n"
        f"Please type the item names and quantities you need.\n"
        f"Example: _Nexgard 3 tablets, Drontal 1 tablet_",
    )
    logger.info("Order category '%s' selected by %s (no recommendations)", category, mask_phone(from_number))


async def handle_recommendation_selection(db: Session, user, text: str) -> None:
    """
    Handle user input after recommendations are shown.
    
    User can:
    - Reply with number(s): "1", "2 3", "1-3" to select recommendations
    - Type custom text to override with custom items
    - Reply "back" to cancel

    Args:
        text: User's response text
    """
    from_number = _get_mobile(user)
    order = _get_active_order(db, user)

    if not order:
        await _abort_stale_flow(db, user, from_number)
        return

    # Check if user said "back" to cancel
    if text.strip().lower() == "back":
        await cancel_order_flow(db, user)
        return

    text_lower = text.strip().lower()

    # Quick shortcut: "usual" / "repeat" selects top saved preferences.
    if text_lower in {"usual", "repeat", "my usual", "usual items", "same as last"}:
        pet = db.query(Pet).filter(Pet.id == order.pet_id).first()
        if not pet:
            await send_text_message(db, from_number, "Error: pet not found. Please try again.")
            return

        top_preferences = get_pet_top_preferences(db, pet.id, str(order.category), limit=3)
        if not top_preferences:
            await send_text_message(
                db,
                from_number,
                "I couldn't find usual items yet. Reply with numbers from the list or type custom items.",
            )
            return

        selected_items = [pref.get("name") for pref in top_preferences if pref.get("name")]
        for item_name in selected_items:
            record_preference(db, pet.id, str(order.category), item_name, "recommendation")

        order.items_description = ", ".join(selected_items)  # type: ignore[assignment]
        db.commit()

        pets = _get_active_pets(db, user)
        if len(pets) == 1:
            await _show_order_confirmation(db, user, order, pet=pets[0])
        elif len(pets) > 1:
            user.order_state = "awaiting_order_pet"
            db.commit()
            pet_list = "\n".join(f"{i+1}. {p.name}" for i, p in enumerate(pets))
            await send_text_message(
                db, from_number,
                f"Which pet is this order for? Reply with the name or number:\n{pet_list}",
            )
        else:
            await _show_order_confirmation(db, user, order, pet=None)
        return

    # Try to parse as number selection (e.g., "1", "2 3", "1-3")
    selected_indices = _parse_number_selection(text)
    
    if selected_indices is not None and len(selected_indices) > 0:
        # User selected recommendations by number
        try:
            # Get recommendations again from DB
            pet = db.query(Pet).filter(Pet.id == order.pet_id).first()
            if not pet:
                await send_text_message(db, from_number, "Error: pet not found. Please try again.")
                return

            recommendations = await _get_numbered_suggestions(
                db,
                pet,
                str(order.category),
                increment_on_hit=False,
            )
            
            # Extract selected items
            selected_items = []
            for idx in selected_indices:
                if 0 < idx <= len(recommendations):
                    item = recommendations[idx - 1]  # Convert to 0-indexed
                    selected_items.append(item.get("name"))
                    # Record as recommendation preference
                    record_preference(
                        db, pet.id, str(order.category), item.get("name"), "recommendation"
                    )
            
            if selected_items:
                # Save selected items to order
                order.items_description = ", ".join(selected_items)  # type: ignore[assignment]
                db.commit()
                
                logger.info(f"User selected {len(selected_items)} recommendation items")
                
                # Continue to pet selection or confirmation
                pets = _get_active_pets(db, user)
                if len(pets) == 1:
                    # Already have pet selected from recommendations
                    await _show_order_confirmation(db, user, order, pet=pets[0])
                elif len(pets) > 1:
                    # Ask for pet selection
                    user.order_state = "awaiting_order_pet"
                    db.commit()
                    pet_list = "\n".join(f"{i+1}. {p.name}" for i, p in enumerate(pets))
                    await send_text_message(
                        db, from_number,
                        f"Which pet is this order for? Reply with the name or number:\n{pet_list}",
                    )
                else:
                    await _show_order_confirmation(db, user, order, pet=None)
                return
            else:
                await send_text_message(
                    db, from_number, 
                    "I didn't find those items in the list. Please try again with valid numbers."
                )
                return
        
        except Exception as e:
            logger.error(f"Error processing recommendation selection: {e}", exc_info=True)
            await send_text_message(db, from_number, "Error processing your selection. Please try again.")
            return
    
    # User provided custom text — treat as free-form items
    await handle_order_items(db, user, text)


async def handle_order_pet_for_recommendation(db: Session, user, text: str) -> None:
    """
    For multi-pet users, choose the pet first, then show AI recommendations.
    """
    from_number = _get_mobile(user)
    order = _get_active_order(db, user)

    if not order:
        await _abort_stale_flow(db, user, from_number)
        return

    pets = _get_active_pets(db, user)
    matched_pet = _match_pet_from_text(pets, text)

    if not matched_pet:
        pet_list = "\n".join(f"{i+1}. {p.name}" for i, p in enumerate(pets))
        await send_text_message(
            db,
            from_number,
            f"I didn't recognize that pet. Please reply with the name or number:\n{pet_list}",
        )
        return

    order.pet_id = matched_pet.id
    db.commit()

    order_category = str(order.category)
    label = ORDER_CATEGORY_LABELS.get(order_category, order_category)
    recommendations = await _get_numbered_suggestions(
        db,
        matched_pet,
        order_category,
        increment_on_hit=True,
    )

    if recommendations:
        user.order_state = "awaiting_reco_sel"
        db.commit()
        await _send_recommendation_list(db, from_number, label, matched_pet.name, recommendations)
        return

    # Fallback if AI/cached recommendations unavailable.
    user.order_state = "awaiting_order_items"
    db.commit()
    await send_text_message(
        db,
        from_number,
        f"*{label}* — got it!\n\n"
        f"Please type the item names and quantities you need.\n"
        f"Example: _Nexgard 3 tablets, Drontal 1 tablet_",
    )


async def _send_recommendation_list(
    db: Session,
    from_number: str,
    category_label: str,
    pet_name: str,
    recommendations: list,
) -> None:
    """Send recommendations in a numbered list with selection instructions."""
    rec_text = f"*{category_label}* for {pet_name}:\n\n"
    for rec in recommendations:
        tag = " (Usual)" if rec.get("source") == "preference" else ""
        rec_text += f"{rec.get('id')}. *{rec.get('name')}*{tag}\n   _{rec.get('description')}_\n\n"

    rec_text += (
        "Reply with:\n"
        "• Number(s) to select items: _1_, _2_, _1 3_, or _1-3_\n"
        "• Or type *usual* / *repeat* for your top saved items\n"
        "• Or type your own items: _Nexgard, Vitamins_\n"
        "• Or reply *back* to cancel"
    )
    await send_text_message(db, from_number, rec_text)


async def _get_numbered_suggestions(
    db: Session,
    pet,
    category: str,
    increment_on_hit: bool,
) -> list:
    """
    Build a combined suggestions list:
    1) user's saved preferences for this pet/category
    2) AI/cached recommendations for profile

    Returns a numbered list with unique names.
    """
    combined = []
    seen = set()

    preferences = get_pet_top_preferences(db, pet.id, category, limit=5)
    for pref in preferences:
        name = str(pref.get("name", "")).strip()
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        combined.append(
            {
                "name": name,
                "description": f"Previously ordered {pref.get('used_count', 0)} time(s)",
                "reason": "From your order history",
                "source": "preference",
            }
        )

    recommendations = await get_or_generate_recommendations(
        db,
        pet,
        category,
        increment_on_hit=increment_on_hit,
    )
    for rec in recommendations:
        name = str(rec.get("name", "")).strip()
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        merged = dict(rec)
        merged["source"] = "ai"
        combined.append(merged)

    for idx, item in enumerate(combined, start=1):
        item["id"] = idx

    return combined


def _parse_number_selection(text: str) -> list | None:
    """
    Parse number selection from text.
    
    Supports: "1", "2 3", "1-3", "1, 2"
    
    Returns:
        List of selected indices (1-indexed), or None if not a number pattern.
        Returns empty list if parsing fails.
    """
    import re
    
    text = text.strip()
    
    # Check if it looks like numbers
    if not re.match(r'^[\d\s\-,]+$', text):
        return None  # Not a number pattern
    
    indices = []
    
    # Split by various delimiters: spaces, commas, hyphens
    # Handle ranges like "1-3"
    parts = re.split(r'[\s,]+', text)
    
    for part in parts:
        if not part:
            continue
        
        if '-' in part:
            # Range like "1-3"
            try:
                start, end = part.split('-')
                start, end = int(start), int(end)
                indices.extend(range(start, end + 1))
            except (ValueError, IndexError):
                pass
        else:
            # Single number
            try:
                indices.append(int(part))
            except ValueError:
                pass
    
    return list(set(indices)) if indices else []  # Remove duplicates


async def handle_order_items(db: Session, user, text: str) -> None:
    """
    Handle items text — save to draft order, then route to pet selection or confirmation.

    Auto-selects pet if user has exactly 1 pet.
    Asks for pet selection if user has 2+ pets.
    Skips pet selection if user has 0 pets.
    
    Records custom item preferences for personalization.
    """
    from_number = _get_mobile(user)
    order = _get_active_order(db, user)

    if not order:
        # Draft order not found — abort flow gracefully.
        await _abort_stale_flow(db, user, from_number)
        return

    # Save items description to the draft order.
    order.items_description = text.strip()[:2000]  # type: ignore[assignment]
    db.commit()

    order_pet_id = getattr(order, "pet_id", None)
    order_category = str(order.category)

    # Record custom preferences (split by commas)
    if order_pet_id is not None:
        # Pet already selected (from recommendations flow)
        pet = db.query(Pet).filter(Pet.id == order_pet_id).first()
        if pet:
            items = [item.strip() for item in order.items_description.split(",")]
            for item in items:
                if item:
                    record_preference(db, pet.id, order_category, item, "custom")

    pets = _get_active_pets(db, user)

    if len(pets) == 0:
        # No pets — skip pet selection, show confirmation without pet.
        await _show_order_confirmation(db, user, order, pet=None)
    elif len(pets) == 1:
        # Auto-select the only pet (if not already selected)
        if getattr(order, "pet_id", None) is None:
            order.pet_id = pets[0].id
            
            # Record custom preferences
            items = [item.strip() for item in order.items_description.split(",")]
            for item in items:
                if item:
                    record_preference(db, pets[0].id, order_category, item, "custom")
        
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
    matched_pet = _match_pet_from_text(pets, text)

    if not matched_pet:
        pet_list = "\n".join(f"{i+1}. {p.name}" for i, p in enumerate(pets))
        await send_text_message(
            db, from_number,
            f"I didn't recognize that pet name. Please reply with the name or number:\n{pet_list}",
        )
        return

    order.pet_id = matched_pet.id

    # If items already entered as custom text, store as preferences now.
    if str(order.items_description).strip():
        items = [item.strip() for item in order.items_description.split(",")]
        for item in items:
            if item:
                record_preference(db, matched_pet.id, str(order.category), item, "custom")

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
        order.status = "pending"  # type: ignore[assignment]
        _clear_order_state(db, user)

        pet_id = getattr(order, "pet_id", None)
        pet = db.query(Pet).filter(Pet.id == pet_id).first() if pet_id is not None else None

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


async def handle_admin_order_status_feedback(db: Session, from_number: str, payload: str) -> None:
    """Handle admin WhatsApp fulfillment feedback and update order status."""

    is_yes = payload.startswith(ORDER_FULFILL_YES_PREFIX)
    is_no = payload.startswith(ORDER_FULFILL_NO_PREFIX)
    if not (is_yes or is_no):
        await send_text_message(db, from_number, "I couldn't process that response.")
        return

    order_id_str = payload.split(":", 1)[1] if ":" in payload else ""
    try:
        order_id = UUID(order_id_str)
    except Exception:
        await send_text_message(db, from_number, "I couldn't identify that order. Please contact support.")
        return

    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        await send_text_message(db, from_number, "Order not found.")
        return

    if is_yes:
        order.status = "completed"  # type: ignore[assignment]
        note = "Admin confirmed via WhatsApp: fulfilled."
        order.admin_notes = f"{order.admin_notes}\n{note}".strip() if order.admin_notes else note  # type: ignore[assignment]
        db.commit()
        await send_text_message(db, from_number, "Marked as fulfilled (completed).")
    else:
        order.status = "cancelled"  # type: ignore[assignment]
        note = "Admin reported via WhatsApp: not fulfilled yet, order cancelled."
        order.admin_notes = f"{order.admin_notes}\n{note}".strip() if order.admin_notes else note  # type: ignore[assignment]
        db.commit()
        await send_text_message(db, from_number, "Marked as not fulfilled yet and cancelled.")


# --- Private Helpers ---


async def _show_order_confirmation(db: Session, user, order: Order, pet) -> None:
    """Send order summary with Confirm/Cancel buttons."""
    from_number = _get_mobile(user)
    order_category = str(order.category)
    label = ORDER_CATEGORY_LABELS.get(order_category, order_category)

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
        order_category = str(order.category)
        label = ORDER_CATEGORY_LABELS.get(order_category, order_category)

        msg = (
            f"New Order Received!\n\n"
            f"User: {user_name}\n"
            f"Phone: {user_phone}\n"
            f"Pet: {pet_name}\n"
            f"Category: {label}\n"
            f"Items: {order.items_description}\n\n"
            "Has this order been fulfilled?"
        )

        buttons = [
            {"id": f"{ORDER_FULFILL_YES_PREFIX}{order.id}", "title": "Yes, fulfilled"},
            {"id": f"{ORDER_FULFILL_NO_PREFIX}{order.id}", "title": "No, order cancelled"},
        ]
        await send_interactive_buttons(db, admin_phone, msg, buttons)
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


def _match_pet_from_text(pets: list, text: str):
    """Match a pet by number or case-insensitive exact name."""
    text_lower = text.strip().lower()

    try:
        idx = int(text_lower) - 1
        if 0 <= idx < len(pets):
            return pets[idx]
    except ValueError:
        pass

    for pet in pets:
        if pet.name.lower() == text_lower:
            return pet

    return None


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
