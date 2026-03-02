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

import logging
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.database import get_db
from app.core.security import validate_admin_key
from app.models.user import User
from app.models.pet import Pet
from app.models.reminder import Reminder
from app.models.document import Document
from app.models.dashboard_token import DashboardToken
from app.models.message_log import MessageLog
from app.models.preventive_record import PreventiveRecord
from app.models.preventive_master import PreventiveMaster


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(validate_admin_key)],
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


@router.get("/users")
def list_users(db: Session = Depends(get_db)):
    """List all registered users with full details."""
    users = db.query(User).all()
    return [
        {
            "id": str(u.id),
            "mobile_number": u.mobile_number,
            "full_name": u.full_name,
            "pincode": u.pincode,
            "email": u.email,
            "consent_given": u.consent_given,
            "onboarding_state": u.onboarding_state,
            "is_deleted": u.is_deleted,
            "created_at": str(u.created_at),
        }
        for u in users
    ]


@router.get("/pets")
def list_pets(db: Session = Depends(get_db)):
    """List all registered pets with owner info."""
    pets = db.query(Pet).all()
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
            raise HTTPException(status_code=400, detail=f"Invalid date: {e}")
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
def list_reminders(db: Session = Depends(get_db)):
    """List all reminders with pet and item details."""
    reminders = (
        db.query(Reminder, PreventiveRecord, PreventiveMaster, Pet)
        .join(PreventiveRecord, Reminder.preventive_record_id == PreventiveRecord.id)
        .join(PreventiveMaster, PreventiveRecord.preventive_master_id == PreventiveMaster.id)
        .join(Pet, PreventiveRecord.pet_id == Pet.id)
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
def list_documents(db: Session = Depends(get_db)):
    """List all uploaded documents with pet info."""
    documents = (
        db.query(Document, Pet)
        .join(Pet, Document.pet_id == Pet.id)
        .all()
    )
    return [
        {
            "id": str(d.id),
            "pet_id": str(d.pet_id),
            "pet_name": p.name,
            "file_path": d.file_path,
            "mime_type": d.mime_type,
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
    return [
        {
            "id": str(m.id),
            "mobile_number": m.mobile_number,
            "direction": m.direction,
            "message_type": m.message_type,
            "payload": m.payload,
            "created_at": str(m.created_at),
        }
        for m in messages
    ]


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
