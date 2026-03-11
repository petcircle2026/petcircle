"""
PetCircle Phase 1 — Admin Panel Router (Module 15)

Provides admin-only API endpoints for managing users, pets,
reminders, documents, message logs, and dashboard tokens.

Security:
    - Every route requires the X-ADMIN-KEY header.
    - The key is validated against ADMIN_SECRET_KEY from environment.
    - No RBAC — single admin key for all operations.
    - Rejected requests return 403 Forbidden.

Routes:
    GET    /admin/stats                      — Aggregated system stats
    GET    /admin/users                      — List all users
    GET    /admin/pets                       — List all pets
    PATCH  /admin/pets/{pet_id}              — Edit pet data
    GET    /admin/reminders                  — List all reminders
    GET    /admin/documents                  — List all documents
    GET    /admin/messages                   — List message logs
    PATCH  /admin/revoke-token/{pet_id}      — Revoke dashboard token
    PATCH  /admin/soft-delete-user/{user_id} — Soft delete a user
    POST   /admin/trigger-reminder/{pet_id}  — Trigger reminder for a pet
"""

import hmac
import logging
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.database import get_db
from app.config import settings
from app.core.security import validate_admin_key
from app.core.rate_limiter import check_admin_rate_limit
from app.core.encryption import decrypt_field
from app.core.log_sanitizer import sanitize_payload
from app.models.user import User
from app.models.pet import Pet
from app.models.reminder import Reminder
from app.models.document import Document
from app.models.dashboard_token import DashboardToken
from app.models.message_log import MessageLog
from app.models.preventive_record import PreventiveRecord
from app.models.preventive_master import PreventiveMaster
from app.models.conflict_flag import ConflictFlag
from app.models.order import Order
from app.models.order_recommendation import OrderRecommendation
from app.models.pet_preference import PetPreference


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(check_admin_rate_limit), Depends(validate_admin_key)],
)


class PetUpdateRequest(BaseModel):
    """Request body for editing pet data."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    species: Optional[str] = Field(None, pattern="^(dog|cat)$")
    breed: Optional[str] = Field(None, max_length=100)
    gender: Optional[str] = Field(None, pattern="^(male|female)$")
    dob: Optional[str] = None
    weight: Optional[float] = Field(None, gt=0, le=999.99)
    neutered: Optional[bool] = None


class OrderStatusUpdate(BaseModel):
    """Request body for updating order status."""
    status: str = Field(..., pattern="^(pending|confirmed|completed|cancelled)$")
    admin_notes: Optional[str] = Field(None, max_length=2000)


def _format_message_payload(message_type: str, payload) -> str:
    """
    Format a message payload for admin display.

    For document/image messages, extracts the filename from the
    webhook payload dict so the admin sees a readable label instead
    of raw JSON.
    """
    if not isinstance(payload, dict):
        return payload if payload else ""

    if message_type == "document":
        # Incoming document webhook payload has nested document.filename
        filename = _extract_filename_from_payload(payload)
        if filename:
            return filename
    elif message_type == "image":
        filename = _extract_filename_from_payload(payload)
        if filename:
            return filename
        # Images often lack a filename — show a label with caption if available.
        caption = _extract_caption_from_payload(payload)
        if caption:
            return f"[Image] {caption}"
        return "[Image]"

    # For text messages, try to extract the body text.
    if message_type == "text":
        text = _extract_text_from_payload(payload)
        if text:
            return text

    # Fallback: return the JSON as a string.
    import json
    try:
        return json.dumps(payload, ensure_ascii=False, default=str)
    except Exception:
        return str(payload)


def _extract_filename_from_payload(payload: dict) -> str | None:
    """Extract filename from nested webhook payload structures."""
    # Direct filename field (from extracted message_data).
    if "filename" in payload:
        return payload["filename"]
    # Nested under document or image object (raw webhook format).
    for key in ("document", "image"):
        obj = payload.get(key)
        if isinstance(obj, dict) and obj.get("filename"):
            return obj["filename"]
    # Check inside entry > changes > messages structure.
    try:
        entries = payload.get("entry", [])
        for entry in entries:
            for change in entry.get("changes", []):
                for msg in change.get("value", {}).get("messages", []):
                    for key in ("document", "image"):
                        obj = msg.get(key)
                        if isinstance(obj, dict) and obj.get("filename"):
                            return obj["filename"]
    except Exception:
        pass
    return None


def _extract_caption_from_payload(payload: dict) -> str | None:
    """Extract caption from image/document payload."""
    if "caption" in payload:
        return payload["caption"]
    for key in ("image", "document"):
        obj = payload.get(key)
        if isinstance(obj, dict) and obj.get("caption"):
            return obj["caption"]
    return None


def _extract_text_from_payload(payload: dict) -> str | None:
    """Extract text body from a text message payload."""
    if "body" in payload:
        return payload["body"]
    text_obj = payload.get("text")
    if isinstance(text_obj, dict):
        return text_obj.get("body")
    if isinstance(text_obj, str):
        return text_obj
    return None


@router.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    """
    Return aggregated system stats for the admin overview dashboard.

    All queries are simple COUNT + GROUP BY — no joins required.
    This avoids N+1 frontend calls by returning everything in one response.
    """
    # --- Users ---
    total_users = db.query(func.count(User.id)).scalar() or 0
    active_users = db.query(func.count(User.id)).filter(User.is_deleted == False).scalar() or 0
    onboarding_complete = (
        db.query(func.count(User.id))
        .filter(User.is_deleted == False, User.onboarding_state == "complete")
        .scalar() or 0
    )
    deleted_users = db.query(func.count(User.id)).filter(User.is_deleted == True).scalar() or 0

    # --- Pets ---
    total_pets = db.query(func.count(Pet.id)).scalar() or 0
    active_pets = db.query(func.count(Pet.id)).filter(Pet.is_deleted == False).scalar() or 0
    dogs = db.query(func.count(Pet.id)).filter(Pet.species == "dog", Pet.is_deleted == False).scalar() or 0
    cats = db.query(func.count(Pet.id)).filter(Pet.species == "cat", Pet.is_deleted == False).scalar() or 0

    # --- Documents ---
    total_docs = db.query(func.count(Document.id)).scalar() or 0
    doc_success = db.query(func.count(Document.id)).filter(Document.extraction_status == "success").scalar() or 0
    doc_pending = db.query(func.count(Document.id)).filter(Document.extraction_status == "pending").scalar() or 0
    doc_failed = db.query(func.count(Document.id)).filter(Document.extraction_status == "failed").scalar() or 0

    # --- Preventive Records ---
    overdue = db.query(func.count(PreventiveRecord.id)).filter(PreventiveRecord.status == "overdue").scalar() or 0
    upcoming = db.query(func.count(PreventiveRecord.id)).filter(PreventiveRecord.status == "upcoming").scalar() or 0
    up_to_date = db.query(func.count(PreventiveRecord.id)).filter(PreventiveRecord.status == "up_to_date").scalar() or 0
    cancelled = db.query(func.count(PreventiveRecord.id)).filter(PreventiveRecord.status == "cancelled").scalar() or 0

    # --- Reminders ---
    total_reminders = db.query(func.count(Reminder.id)).scalar() or 0
    rem_pending = db.query(func.count(Reminder.id)).filter(Reminder.status == "pending").scalar() or 0
    rem_sent = db.query(func.count(Reminder.id)).filter(Reminder.status == "sent").scalar() or 0
    rem_completed = db.query(func.count(Reminder.id)).filter(Reminder.status == "completed").scalar() or 0
    rem_snoozed = db.query(func.count(Reminder.id)).filter(Reminder.status == "snoozed").scalar() or 0

    # --- Conflicts ---
    pending_conflicts = db.query(func.count(ConflictFlag.id)).filter(ConflictFlag.status == "pending").scalar() or 0

    # --- Orders ---
    total_orders = db.query(func.count(Order.id)).scalar() or 0
    orders_pending = db.query(func.count(Order.id)).filter(Order.status == "pending").scalar() or 0
    orders_confirmed = db.query(func.count(Order.id)).filter(Order.status == "confirmed").scalar() or 0
    orders_completed = db.query(func.count(Order.id)).filter(Order.status == "completed").scalar() or 0
    orders_cancelled = db.query(func.count(Order.id)).filter(Order.status == "cancelled").scalar() or 0

    # --- Messages in last 24h ---
    cutoff = datetime.utcnow() - timedelta(hours=24)
    messages_24h = db.query(func.count(MessageLog.id)).filter(MessageLog.created_at >= cutoff).scalar() or 0

    return {
        "users": {
            "total": total_users,
            "active": active_users,
            "onboarding_complete": onboarding_complete,
            "deleted": deleted_users,
        },
        "pets": {
            "total": total_pets,
            "active": active_pets,
            "dogs": dogs,
            "cats": cats,
        },
        "documents": {
            "total": total_docs,
            "success": doc_success,
            "pending": doc_pending,
            "failed": doc_failed,
        },
        "preventive_records": {
            "overdue": overdue,
            "upcoming": upcoming,
            "up_to_date": up_to_date,
            "cancelled": cancelled,
        },
        "reminders": {
            "total": total_reminders,
            "pending": rem_pending,
            "sent": rem_sent,
            "completed": rem_completed,
            "snoozed": rem_snoozed,
        },
        "conflicts": {
            "pending": pending_conflicts,
        },
        "orders": {
            "total": total_orders,
            "pending": orders_pending,
            "confirmed": orders_confirmed,
            "completed": orders_completed,
            "cancelled": orders_cancelled,
        },
        "messages_24h": messages_24h,
    }


@router.get("/users")
def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """List registered users with pagination."""
    users = db.query(User).offset(skip).limit(limit).all()
    # Decrypt PII fields for admin response (full numbers, no masking).
    return [
        {
            "id": str(u.id),
            "mobile_number": decrypt_field(u.mobile_number),
            "full_name": u.full_name,
            "pincode": decrypt_field(u.pincode) if u.pincode else None,
            "email": decrypt_field(u.email) if u.email else None,
            "consent_given": u.consent_given,
            "onboarding_state": u.onboarding_state,
            "is_deleted": u.is_deleted,
            "created_at": str(u.created_at),
        }
        for u in users
    ]


@router.get("/pets")
def list_pets(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """List registered pets with pagination."""
    pets = db.query(Pet).offset(skip).limit(limit).all()
    return [
        {
            "id": str(p.id),
            "user_id": str(p.user_id),
            "name": p.name,
            "species": p.species,
            "breed": p.breed,
            "gender": p.gender,
            "dob": str(p.dob) if p.dob else None,
            "weight": float(p.weight) if p.weight else None,
            "neutered": p.neutered,
            "is_deleted": p.is_deleted,
            "created_at": str(p.created_at),
        }
        for p in pets
    ]


@router.patch("/pets/{pet_id}")
def edit_pet(pet_id: UUID, body: PetUpdateRequest, db: Session = Depends(get_db)):
    """
    Edit pet data. Only provided fields are updated.

    Args:
        pet_id: UUID of the pet to edit.
        body: PetUpdateRequest with fields to update.

    Raises:
        HTTPException 404: If pet not found.
    """
    pet = db.query(Pet).filter(Pet.id == pet_id).first()
    if not pet:
        raise HTTPException(status_code=404, detail="Pet not found.")

    updated_fields = []

    if body.name is not None:
        pet.name = body.name
        updated_fields.append("name")
    if body.species is not None:
        pet.species = body.species
        updated_fields.append("species")
    if body.breed is not None:
        pet.breed = body.breed
        updated_fields.append("breed")
    if body.gender is not None:
        pet.gender = body.gender
        updated_fields.append("gender")
    if body.dob is not None:
        from app.utils.date_utils import parse_date
        try:
            pet.dob = parse_date(body.dob)
            updated_fields.append("dob")
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail="Invalid date format. Use DD/MM/YYYY, DD-MM-YYYY, or YYYY-MM-DD.",
            )
    if body.weight is not None:
        pet.weight = body.weight
        updated_fields.append("weight")
    if body.neutered is not None:
        pet.neutered = body.neutered
        updated_fields.append("neutered")

    if not updated_fields:
        return {"status": "no_changes", "pet_id": str(pet_id)}

    db.commit()
    logger.info("Pet edited: pet_id=%s, fields=%s", str(pet_id), updated_fields)

    return {
        "status": "updated",
        "pet_id": str(pet_id),
        "updated_fields": updated_fields,
    }


@router.get("/reminders")
def list_reminders(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """List reminders with pet and item details (paginated)."""
    reminders = (
        db.query(Reminder, PreventiveRecord, PreventiveMaster, Pet)
        .join(PreventiveRecord, Reminder.preventive_record_id == PreventiveRecord.id)
        .join(PreventiveMaster, PreventiveRecord.preventive_master_id == PreventiveMaster.id)
        .join(Pet, PreventiveRecord.pet_id == Pet.id)
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [
        {
            "id": str(r.id),
            "pet_name": p.name,
            "item_name": m.item_name,
            "next_due_date": str(r.next_due_date),
            "record_status": rec.status,
            "reminder_status": r.status,
            "sent_at": str(r.sent_at) if r.sent_at else None,
            "created_at": str(r.created_at),
        }
        for r, rec, m, p in reminders
    ]


@router.get("/documents")
def list_documents(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """List uploaded documents with pet info (paginated)."""
    documents = (
        db.query(Document, Pet)
        .join(Pet, Document.pet_id == Pet.id)
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [
        {
            "id": str(d.id),
            "pet_id": str(d.pet_id),
            "pet_name": p.name,
            "document_name": d.document_name or d.file_path.split("/")[-1],
            "extraction_status": d.extraction_status,
            "created_at": str(d.created_at),
        }
        for d, p in documents
    ]


@router.get("/messages")
def list_messages(
    direction: Optional[str] = Query(None, pattern="^(incoming|outgoing)$"),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """
    List message logs for audit and debugging.

    Args:
        direction: Filter by 'incoming' or 'outgoing'. None for all.
        limit: Max number of results (default 100, max 1000).
    """
    query = db.query(MessageLog).order_by(MessageLog.created_at.desc())

    if direction:
        query = query.filter(MessageLog.direction == direction)

    messages = query.limit(limit).all()
    # Sanitize payloads in admin response — show full mobile numbers.
    results = []
    for m in messages:
        payload = sanitize_payload(m.payload) if isinstance(m.payload, dict) else m.payload
        # For document/image messages, show a readable label with filename
        # instead of raw webhook JSON.
        display_payload = _format_message_payload(m.message_type, payload)
        results.append({
            "id": str(m.id),
            "mobile_number": m.mobile_number,
            "direction": m.direction,
            "message_type": m.message_type,
            "payload": display_payload,
            "created_at": str(m.created_at),
        })
    return results


@router.get("/orders")
def list_orders(
    status: Optional[str] = Query(None, pattern="^(pending|confirmed|completed|cancelled)$"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """List orders with optional status filter and pagination."""
    query = db.query(Order).order_by(Order.created_at.desc())

    if status:
        query = query.filter(Order.status == status)

    orders = query.offset(skip).limit(limit).all()
    results = []
    for o in orders:
        # Resolve user name and pet name via relationships.
        user = db.query(User).filter(User.id == o.user_id).first()
        pet = db.query(Pet).filter(Pet.id == o.pet_id).first() if o.pet_id else None

        user_name = user.full_name if user else "Unknown"
        user_phone = decrypt_field(user.mobile_number) if user else "Unknown"
        pet_name = pet.name if pet else None

        results.append({
            "id": str(o.id),
            "user_id": str(o.user_id),
            "user_name": user_name,
            "user_phone": user_phone,
            "pet_id": str(o.pet_id) if o.pet_id else None,
            "pet_name": pet_name,
            "category": o.category,
            "items_description": o.items_description,
            "status": o.status,
            "admin_notes": o.admin_notes,
            "created_at": str(o.created_at),
            "updated_at": str(o.updated_at),
        })

    return results


@router.patch("/orders/{order_id}/status")
def update_order_status(
    order_id: UUID,
    body: OrderStatusUpdate,
    db: Session = Depends(get_db),
):
    """
    Update order status and optionally add admin notes.

    Valid transitions: any status → any status (admin has full control).
    """
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found.")

    old_status = order.status
    order.status = body.status  # type: ignore[assignment]
    if body.admin_notes is not None:
        order.admin_notes = body.admin_notes  # type: ignore[assignment]

    db.commit()

    logger.info(
        "Order status updated: order_id=%s, %s → %s",
        str(order_id), old_status, body.status,
    )

    return {
        "status": "updated",
        "order_id": str(order_id),
        "old_status": old_status,
        "new_status": body.status,
    }


@router.get("/order-recommendations")
def list_order_recommendations(
    species: Optional[str] = Query(None, pattern="^(dog|cat)$"),
    category: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """
    List cached recommendation profiles.
    
    Useful for understanding what combinations have been recommended
    and how often they're being reused.
    """
    query = db.query(OrderRecommendation).order_by(OrderRecommendation.used_count.desc())

    if species:
        query = query.filter(OrderRecommendation.species == species)
    
    if category:
        query = query.filter(OrderRecommendation.category == category)

    recommendations = query.offset(skip).limit(limit).all()
    
    results = []
    for rec in recommendations:
        results.append({
            "id": str(rec.id),
            "species": rec.species,
            "breed": rec.breed,
            "age_range": rec.age_range,
            "category": rec.category,
            "item_count": len(rec.items) if rec.items else 0,
            "items": rec.items,
            "used_count": rec.used_count,
            "created_at": str(rec.created_at),
            "updated_at": str(rec.updated_at),
        })

    return results


@router.get("/pet-preferences/{pet_id}")
def list_pet_preferences(
    pet_id: UUID,
    category: Optional[str] = Query(None),
    preference_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """
    List all preferences (ordered items) for a specific pet.
    
    Shows both items from recommendation lists and custom items.
    Helps understand pet owner ordering patterns.
    """
    # Verify pet exists
    pet = db.query(Pet).filter(Pet.id == pet_id).first()
    if not pet:
        raise HTTPException(status_code=404, detail="Pet not found.")

    query = db.query(PetPreference).filter(
        PetPreference.pet_id == pet_id
    ).order_by(PetPreference.used_count.desc())

    if category:
        query = query.filter(PetPreference.category == category)
    
    if preference_type:
        query = query.filter(PetPreference.preference_type == preference_type)

    preferences = query.all()
    
    results = []
    for pref in preferences:
        results.append({
            "id": str(pref.id),
            "pet_id": str(pref.pet_id),
            "category": pref.category,
            "item_name": pref.item_name,
            "preference_type": pref.preference_type,
            "used_count": pref.used_count,
            "created_at": str(pref.created_at),
            "updated_at": str(pref.updated_at),
        })

    return {
        "pet_id": str(pet_id),
        "pet_name": pet.name,
        "species": pet.species,
        "preferences": results,
    }


@router.get("/preferences-stats")
def preferences_stats(
    db: Session = Depends(get_db),
):
    """
    Get statistics about preferences across all users.
    
    Shows popular items, most used categories, etc.
    """
    total_preferences = db.query(func.count(PetPreference.id)).scalar() or 0
    total_recommendations = db.query(func.count(OrderRecommendation.id)).scalar() or 0
    
    # Most used items
    most_used_items = (
        db.query(
            PetPreference.item_name,
            PetPreference.category,
            func.sum(PetPreference.used_count).label("total_uses")
        )
        .group_by(PetPreference.item_name, PetPreference.category)
        .order_by(func.sum(PetPreference.used_count).desc())
        .limit(20)
        .all()
    )
    
    # Most popular recommendations
    most_used_recs = (
        db.query(
            OrderRecommendation.species,
            OrderRecommendation.breed,
            OrderRecommendation.category,
            OrderRecommendation.used_count
        )
        .order_by(OrderRecommendation.used_count.desc())
        .limit(20)
        .all()
    )
    
    # Preference type breakdown
    pref_type_breakdown = (
        db.query(
            PetPreference.preference_type,
            func.count(PetPreference.id).label("count")
        )
        .group_by(PetPreference.preference_type)
        .all()
    )
    
    return {
        "total_preferences": total_preferences,
        "total_recommendations": total_recommendations,
        "most_used_items": [
            {
                "item_name": item[0],
                "category": item[1],
                "total_uses": item[2],
            }
            for item in most_used_items
        ],
        "most_popular_recommendations": [
            {
                "species": rec[0],
                "breed": rec[1],
                "category": rec[2],
                "used_count": rec[3],
            }
            for rec in most_used_recs
        ],
        "preference_type_breakdown": [
            {
                "type": breakdown[0],
                "count": breakdown[1],
            }
            for breakdown in pref_type_breakdown
        ],
    }


@router.patch("/revoke-token/{pet_id}")
def revoke_dashboard_token(pet_id: UUID, db: Session = Depends(get_db)):
    """Revoke the dashboard token for a specific pet (soft operation)."""
    token = (
        db.query(DashboardToken)
        .filter(DashboardToken.pet_id == pet_id, DashboardToken.revoked == False)
        .first()
    )

    if not token:
        raise HTTPException(
            status_code=404,
            detail="No active dashboard token found for this pet.",
        )

    token.revoked = True
    db.commit()
    logger.info("Dashboard token revoked for pet_id=%s", str(pet_id))
    return {"status": "revoked", "pet_id": str(pet_id)}


@router.patch("/soft-delete-user/{user_id}")
def soft_delete_user(user_id: UUID, db: Session = Depends(get_db)):
    """Soft delete a user — sets is_deleted=True, preserves data."""
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    if user.is_deleted:
        return {"status": "already_deleted", "user_id": str(user_id)}

    user.is_deleted = True
    db.commit()
    logger.info("User soft-deleted: user_id=%s", str(user_id))
    return {"status": "soft_deleted", "user_id": str(user_id)}


@router.post("/trigger-reminder/{pet_id}")
def trigger_reminder_for_pet(pet_id: UUID, db: Session = Depends(get_db)):
    """
    Manually trigger reminder processing for a specific pet.

    Finds all upcoming/overdue preventive records for this pet
    and creates pending reminders for them.
    """
    pet = db.query(Pet).filter(Pet.id == pet_id).first()
    if not pet:
        raise HTTPException(status_code=404, detail="Pet not found.")

    from app.services.reminder_engine import run_reminder_engine
    results = run_reminder_engine(db)

    logger.info(
        "Manual reminder trigger for pet_id=%s: %s",
        str(pet_id), str(results),
    )
    return {"status": "triggered", "pet_id": str(pet_id), "results": results}


@router.post("/verify-key")
def verify_admin_key_endpoint():
    """
    Verify admin key validity.

    This endpoint exists solely for the frontend login form to validate
    the admin key server-side before showing the admin UI.
    The actual validation is handled by the router-level
    validate_admin_key dependency — if execution reaches this function,
    the key is valid.

    Returns:
        {"valid": true} if the key is accepted (403 otherwise via dependency).
    """
    return {"valid": True}


class AdminLoginRequest(BaseModel):
    """Request body for admin dashboard login."""
    password: str


# Login endpoint is separate from the main router — no admin key required.
# Rate limiting is applied to prevent brute-force password guessing.
login_router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(check_admin_rate_limit)],
)


@login_router.post("/login")
def admin_login(body: AdminLoginRequest):
    """
    Authenticate admin dashboard users with a password.

    Validates the password against ADMIN_DASHBOARD_PASSWORD.
    On success, returns the ADMIN_SECRET_KEY so the frontend can
    make subsequent authenticated API calls.

    This endpoint does NOT require the X-ADMIN-KEY header — the user
    doesn't have the key yet; they're logging in to receive it.

    Returns:
        {"valid": true, "admin_key": "<ADMIN_SECRET_KEY>"} on success.

    Raises:
        HTTPException 403: If the password is incorrect.
    """
    # Constant-time comparison to prevent timing attacks.
    if not hmac.compare_digest(body.password, settings.ADMIN_DASHBOARD_PASSWORD):
        logger.warning("Admin dashboard login failed — invalid password.")
        raise HTTPException(
            status_code=403,
            detail="Invalid password.",
        )

    logger.info("Admin dashboard login successful.")
    return {"valid": True, "admin_key": settings.ADMIN_SECRET_KEY}
