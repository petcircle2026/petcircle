"""
PetCircle Phase 1 — Strict Query Engine (Module 14)

Answers user questions about their pet's health records using OpenAI GPT.
The model is strictly grounded in the pet's data — no external knowledge,
no medical advice, no hallucinated information.

Model configuration (from constants — never hardcoded):
    - Model: OPENAI_QUERY_MODEL (gpt-4.1-mini)
    - Temperature: 0 (deterministic responses)
    - Max tokens: 1500

System prompt enforces strict grounding:
    - Only answer using provided data.
    - If information is unavailable, say exactly:
      "I don't have that information in your pet's records."
    - No medical advice.
    - No external knowledge.

Retry policy:
    - Uses retry_openai_call() from utils/retry.py.
    - 3 attempts (1s, 2s backoff) — from constants.
    - On final failure: return error message, never crash.

Context building:
    - Pet profile (name, species, breed, age, weight).
    - Preventive records (item names, dates, statuses).
    - Reminders (upcoming items and due dates).
    - Documents (upload history and extraction status).
    - Health score.

Rules:
    - All model config from constants.py.
    - API key from settings (env var) — never hardcoded.
    - No medical advice under any circumstances.
    - If data not available, explicit "I don't have that information" response.
"""

import logging
from uuid import UUID
from sqlalchemy.orm import Session
from app.models.pet import Pet
from app.models.user import User
from app.models.preventive_record import PreventiveRecord
from app.models.preventive_master import PreventiveMaster
from app.models.reminder import Reminder
from app.models.document import Document
from app.core.constants import (
    OPENAI_QUERY_MODEL,
    OPENAI_EXTRACTION_TEMPERATURE,
    OPENAI_EXTRACTION_MAX_TOKENS,
    HEALTH_SCORE_ESSENTIAL_WEIGHT,
    HEALTH_SCORE_COMPLEMENTARY_WEIGHT,
)
from app.config import settings
from app.utils.retry import retry_openai_call


logger = logging.getLogger(__name__)

_openai_query_client = None


def _get_openai_query_client():
    """Return a cached AsyncOpenAI client for queries (created on first call)."""
    global _openai_query_client
    if _openai_query_client is None:
        from openai import AsyncOpenAI
        _openai_query_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _openai_query_client


# --- System prompt for strict query engine ---
# Enforces grounding: only use provided data, no external knowledge.
# Exact wording from Module 14 specification.
QUERY_SYSTEM_PROMPT = (
    "You may ONLY answer using provided data. "
    "If information is not available, say: "
    "I don't have that information in your pet's records.\n\n"
    "Rules:\n"
    "- Do NOT provide medical advice.\n"
    "- Do NOT use external knowledge.\n"
    "- Do NOT guess or infer information not present in the data.\n"
    "- Answer concisely and clearly.\n"
    "- Refer to the pet by name when available."
)


def _build_pet_context(db: Session, pet_id: UUID) -> str:
    """
    Build a text context string from the pet's database records.

    This context is passed to GPT as the data source for answering
    questions. It includes all relevant information the user might
    ask about, structured for clarity.

    Data included:
        - Pet profile (name, species, breed, gender, dob, weight, neutered).
        - Preventive records (item name, last done, next due, status).
        - Active reminders (item name, due date, status).
        - Documents (count, types, extraction statuses).
        - Health score (overall and category breakdown).

    All data is read from DB — no hardcoded values.

    Args:
        db: SQLAlchemy database session.
        pet_id: UUID of the pet.

    Returns:
        Formatted text string with all pet data for GPT context.
    """
    # --- Pet profile ---
    pet = db.query(Pet).filter(Pet.id == pet_id).first()
    if not pet:
        return "No pet data available."

    user = db.query(User).filter(User.id == pet.user_id).first()

    context_parts = []

    # Pet profile section.
    context_parts.append("=== Pet Profile ===")
    context_parts.append(f"Name: {pet.name}")
    context_parts.append(f"Species: {pet.species}")
    if pet.breed:
        context_parts.append(f"Breed: {pet.breed}")
    if pet.gender:
        context_parts.append(f"Gender: {pet.gender}")
    if pet.dob:
        context_parts.append(f"Date of Birth: {pet.dob}")
    if pet.weight:
        context_parts.append(f"Weight: {pet.weight} kg")
    if pet.neutered is not None:
        context_parts.append(f"Neutered: {'Yes' if pet.neutered else 'No'}")
    if user:
        context_parts.append(f"Owner: {user.full_name}")

    # --- Preventive records ---
    # Recurrence and item data always from preventive_master in DB.
    records = (
        db.query(PreventiveRecord, PreventiveMaster)
        .join(
            PreventiveMaster,
            PreventiveRecord.preventive_master_id == PreventiveMaster.id,
        )
        .filter(PreventiveRecord.pet_id == pet_id)
        .order_by(PreventiveRecord.next_due_date.asc())
        .all()
    )

    # Compute health score inline from the same records query
    # to avoid a redundant DB round-trip via compute_health_score().
    essential_done, essential_total = 0, 0
    complementary_done, complementary_total = 0, 0

    context_parts.append("\n=== Preventive Health Records ===")
    if records:
        for record, master in records:
            context_parts.append(
                f"- {master.item_name} ({master.category}): "
                f"Last done: {record.last_done_date}, "
                f"Next due: {record.next_due_date}, "
                f"Status: {record.status}"
            )
            # Accumulate health score counts from the same data.
            if record.status != "cancelled":
                if master.category == "essential":
                    essential_total += 1
                    if record.status == "up_to_date":
                        essential_done += 1
                elif master.category == "complete":
                    complementary_total += 1
                    if record.status == "up_to_date":
                        complementary_done += 1
    else:
        context_parts.append("No preventive records found.")

    # --- Reminders ---
    reminders = (
        db.query(Reminder, PreventiveRecord, PreventiveMaster)
        .join(
            PreventiveRecord,
            Reminder.preventive_record_id == PreventiveRecord.id,
        )
        .join(
            PreventiveMaster,
            PreventiveRecord.preventive_master_id == PreventiveMaster.id,
        )
        .filter(
            PreventiveRecord.pet_id == pet_id,
            Reminder.status.in_(["pending", "sent"]),
        )
        .order_by(Reminder.next_due_date.asc())
        .all()
    )

    context_parts.append("\n=== Active Reminders ===")
    if reminders:
        for reminder, record, master in reminders:
            context_parts.append(
                f"- {master.item_name}: Due {reminder.next_due_date}, "
                f"Status: {reminder.status}"
            )
    else:
        context_parts.append("No active reminders.")

    # --- Documents ---
    documents = (
        db.query(Document)
        .filter(Document.pet_id == pet_id)
        .all()
    )

    context_parts.append("\n=== Uploaded Documents ===")
    if documents:
        context_parts.append(f"Total documents: {len(documents)}")
        status_counts = {}
        for doc in documents:
            status_counts[doc.extraction_status] = (
                status_counts.get(doc.extraction_status, 0) + 1
            )
        for status, count in status_counts.items():
            context_parts.append(f"- {status}: {count}")
    else:
        context_parts.append("No documents uploaded.")

    # --- Health score (computed inline from records already loaded above) ---
    e_ratio = essential_done / essential_total if essential_total > 0 else 0.0
    c_ratio = complementary_done / complementary_total if complementary_total > 0 else 0.0
    score = round(
        (e_ratio * HEALTH_SCORE_ESSENTIAL_WEIGHT + c_ratio * HEALTH_SCORE_COMPLEMENTARY_WEIGHT) * 100
    )

    context_parts.append("\n=== Health Score ===")
    context_parts.append(f"Overall Score: {score}/100")
    context_parts.append(
        f"Essential items: {essential_done}/{essential_total} up to date"
    )
    context_parts.append(
        f"Complementary items: {complementary_done}/{complementary_total} up to date"
    )

    return "\n".join(context_parts)


async def answer_pet_question(
    db: Session,
    pet_id: UUID,
    question: str,
) -> dict:
    """
    Answer a user's question about their pet using GPT.

    The model is strictly grounded in the pet's database records.
    No external knowledge, no medical advice.

    Pipeline:
        1. Build context from pet's DB records.
        2. Send context + question to GPT (gpt-4.1-mini from constants).
        3. Return the grounded answer.

    On GPT failure:
        - Return a user-friendly error message.
        - Never crash the application.

    Args:
        db: SQLAlchemy database session.
        pet_id: UUID of the pet being queried.
        question: The user's question text.

    Returns:
        Dictionary with:
            - answer: GPT's grounded response.
            - status: 'success' or 'error'.
    """
    # Build context from pet's database records.
    context = _build_pet_context(db, pet_id)

    # Construct the user message with context and question.
    user_message = (
        f"Here is the pet's data:\n\n{context}\n\n"
        f"User question: {question}"
    )

    try:
        # Reuse cached client — avoids recreating on every query.
        client = _get_openai_query_client()

        async def _make_call() -> str:
            """Inner function wrapped by retry_openai_call."""
            response = await client.chat.completions.create(
                model=OPENAI_QUERY_MODEL,
                temperature=OPENAI_EXTRACTION_TEMPERATURE,
                max_tokens=OPENAI_EXTRACTION_MAX_TOKENS,
                messages=[
                    {"role": "system", "content": QUERY_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
            )
            return response.choices[0].message.content

        # Retry with backoff: 3 attempts (1s, 2s) — from constants.
        answer = await retry_openai_call(_make_call)

        logger.info(
            "Query answered: pet_id=%s, question_length=%d, "
            "answer_length=%d",
            str(pet_id),
            len(question),
            len(answer) if answer else 0,
        )

        return {
            "answer": answer,
            "status": "success",
        }

    except Exception as e:
        # GPT failure — return user-friendly error, never crash.
        logger.error(
            "Query engine failed: pet_id=%s, error=%s",
            str(pet_id),
            str(e),
        )

        return {
            "answer": (
                "I'm sorry, I'm unable to process your question right now. "
                "Please try again later."
            ),
            "status": "error",
        }
