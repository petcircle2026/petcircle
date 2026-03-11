"""
PetCircle — Recommendation Service

Generates AI-powered product recommendations for pets based on:
- Species (dog/cat)
- Breed
- Age
- Category (medicines, food_nutrition, supplements)

Workflow:
1. Check if a recommendation exists for this pet's profile.
2. If not found, call OpenAI to generate recommendations.
3. Store the recommendation in the database for future reuse.
4. Return the recommendations to the order flow.

Retry policy:
- 3 attempts with exponential backoff (1s, 2s)
- On failure, return an empty list (user can still type custom items)
"""

import logging
import json
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import and_, func
from app.models.order_recommendation import OrderRecommendation
from app.models.pet_preference import PetPreference
from app.core.constants import (
    OPENAI_QUERY_MODEL,
    ORDER_CAT_MEDICINES,
    ORDER_CAT_FOOD,
    ORDER_CAT_SUPPLEMENTS,
)
from app.config import settings
from app.utils.retry import retry_openai_call

logger = logging.getLogger(__name__)

_openai_recommendation_client = None


def _get_openai_client():
    """Return a cached AsyncOpenAI client for recommendations."""
    global _openai_recommendation_client
    if _openai_recommendation_client is None:
        from openai import AsyncOpenAI
        _openai_recommendation_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _openai_recommendation_client


def _calculate_age_range(dob) -> str:
    """
    Calculate age range from date of birth.
    
    Returns:
        - "0-2_months" for 0-2 months old (puppies/kittens)
        - "2-6_months" for 2-6 months
        - "6-12_months" for 6-12 months
        - "1-3_years" for 1-3 years (young adult)
        - "3-7_years" for 3-7 years (adult)
        - "7+_years" for 7+ years (senior)
        - "unknown" if no dob provided
    """
    if not dob:
        return "unknown"

    now = datetime.utcnow().date()
    age_days = (now - dob).days

    if age_days < 60:  # ~2 months
        return "0-2_months"
    elif age_days < 180:  # ~6 months
        return "2-6_months"
    elif age_days < 365:  # ~12 months
        return "6-12_months"
    elif age_days < 1095:  # ~3 years
        return "1-3_years"
    elif age_days < 2555:  # ~7 years
        return "3-7_years"
    else:
        return "7+_years"


def _get_category_description(category: str) -> str:
    """Get a readable description for a category."""
    category_map = {
        ORDER_CAT_MEDICINES: "Medicines",
        ORDER_CAT_FOOD: "Food & Nutrition",
        ORDER_CAT_SUPPLEMENTS: "Supplements",
    }
    return category_map.get(category, category)


async def get_or_generate_recommendations(
    db: Session,
    pet,
    category,
    increment_on_hit: bool = True,
) -> list:
    """
    Get recommendations for a pet, from cache or AI generation.
    
    Args:
        db: Database session
        pet: Pet object with species, breed, dob
        category: Order category (medicines, food_nutrition, supplements)
    
    Returns:
        List of recommendation items as dicts:
        [
            {
                "id": 1,
                "name": "Product Name",
                "description": "Brief description",
                "reason": "Why recommended"
            },
            ...
        ]
        Returns empty list on error.
    """
    try:
        pet_species = str(getattr(pet, "species", ""))
        pet_breed_value = getattr(pet, "breed", None)
        pet_breed = str(pet_breed_value) if pet_breed_value else None
        age_range = _calculate_age_range(pet.dob)
        
        # Check database for existing recommendation
        existing = db.query(OrderRecommendation).filter(
            and_(
                OrderRecommendation.species == pet_species,
                OrderRecommendation.breed == pet_breed,
                OrderRecommendation.age_range == age_range,
                OrderRecommendation.category == category,
            )
        ).first()
        
        if existing:
            # Increment usage count when this recommendation is actually surfaced.
            if increment_on_hit:
                existing.used_count = (getattr(existing, "used_count", 0) or 0) + 1  # type: ignore[assignment]
                db.commit()
            
            logger.info(
                f"Using cached recommendation for {pet_species} "
                f"(breed={pet_breed}, age={age_range}, category={category})"
            )
            
            # Convert JSON items to list with IDs
            items = []
            raw_items = getattr(existing, "items", []) or []
            for idx, item in enumerate(raw_items if isinstance(raw_items, list) else [], start=1):
                if isinstance(item, dict):
                    enriched = dict(item)
                    enriched["id"] = idx
                    items.append(enriched)
            return items
        
        # No cache hit — generate via AI
        logger.info(
            f"Generating new recommendation for {pet_species} "
            f"(breed={pet_breed}, age={age_range}, category={category})"
        )
        
        items = await _generate_recommendations_via_ai(
            pet_species,
            pet_breed,
            age_range,
            category,
        )
        
        # Store in database for future reuse
        if items:
            recommendation = OrderRecommendation(
                pet_id=getattr(pet, "id", None),
                species=pet_species,
                breed=pet_breed,
                age_range=age_range,
                category=category,
                items=[{k: v for k, v in item.items() if k != "id"} for item in items],
                used_count=1,
            )
            db.add(recommendation)
            db.commit()
            
            # Add IDs for response
            for idx, item in enumerate(items, start=1):
                item["id"] = idx
        
        return items
    
    except Exception as e:
        logger.error(f"Failed to get recommendations: {e}", exc_info=True)
        return []


async def _generate_recommendations_via_ai(
    species: str,
    breed: str | None,
    age_range: str,
    category: str,
) -> list:
    """
    Call OpenAI to generate recommendations.
    
    Returns:
        List of items without IDs or empty list on failure.
    """
    client = _get_openai_client()
    category_display = _get_category_description(category)
    
    prompt = _build_recommendation_prompt(
        species, breed, age_range, category_display
    )
    
    try:
        response = await retry_openai_call(
            client.chat.completions.create,
            model=OPENAI_QUERY_MODEL,
            temperature=0.7,  # Slightly higher for more varied recommendations
            max_tokens=1500,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a veterinary expert recommending pet products. "
                        "Always respond with valid JSON. "
                        "Never include explanations outside the JSON."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
        )
        
        # Parse the response
        response_text = response.choices[0].message.content.strip()
        
        # Try to extract JSON from response
        items = _extract_json_from_response(response_text)
        
        if not items:
            logger.warning(
                f"Failed to parse AI response for {species}/{breed}/{age_range}/{category}: {response_text}"
            )
            return []
        
        # Validate and clean items
        cleaned_items = []
        for item in items:
            if isinstance(item, dict) and "name" in item:
                cleaned_items.append({
                    "name": str(item.get("name", ""))[:200],
                    "description": str(item.get("description", ""))[:500],
                    "reason": str(item.get("reason", ""))[:300],
                })
        
        logger.info(f"Generated {len(cleaned_items)} recommendations via AI")
        return cleaned_items
    
    except Exception as e:
        logger.error(
            f"OpenAI API error generating recommendations: {e}", exc_info=True
        )
        return []


def _build_recommendation_prompt(
    species: str,
    breed: str | None,
    age_range: str,
    category_display: str,
) -> str:
    """Build the prompt for AI recommendation generation."""
    breed_info = f" ({breed})" if breed else ""
    
    return (
        f"Recommend 5-7 {category_display.lower()} for a {age_range} {species}{breed_info}.\n\n"
        f"Return ONLY a JSON array with no markdown formatting, like this:\n"
        f"[\n"
        f'  {{"name": "Product Name", "description": "Short description", "reason": "Why recommended"}},\n'
        f"  ...\n"
        f"]\n\n"
        f"Requirements:\n"
        f"- Each product must be real and vet-recommended for {species}s\n"
        f"- Include specific brand names where appropriate\n"
        f"- Focus on {age_range} {species.lower()}s' specific needs\n"
        f"- Keep descriptions under 50 words\n"
        f"- Keep reasons under 30 words"
    )


def _extract_json_from_response(response_text: str) -> list:
    """
    Extract JSON array from AI response.
    
    Handles responses with markdown code blocks.
    """
    # Try direct parse first
    try:
        return json.loads(response_text)
    except json.JSONDecodeError:
        pass
    
    # Try to find JSON within markdown code blocks
    import re
    
    # Match ```json ... ``` or ```...```
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", response_text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    
    # Try to find raw JSON array
    match = re.search(r"\[.*\]", response_text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    
    return []


def record_preference(
    db: Session,
    pet_id,
    category,
    item_name,
    preference_type: str = "custom",
) -> None:
    """
    Record that a user ordered an item (preference).
    
    If this item was previously ordered, increment used_count.
    Otherwise, create a new preference record.
    
    Args:
        db: Database session
        pet_id: Pet UUID
        category: Order category
        item_name: Item name
        preference_type: "recommendation" or "custom"
    """
    try:
        normalized_name = item_name.strip()
        if not normalized_name:
            return

        # Case-insensitive match to avoid duplicates like "Nexgard" vs "nexgard".
        existing = (
            db.query(PetPreference)
            .filter(
                PetPreference.pet_id == pet_id,
                PetPreference.category == category,
                func.lower(PetPreference.item_name) == normalized_name.lower(),
            )
            .first()
        )
        
        if existing:
            existing.used_count = (getattr(existing, "used_count", 0) or 0) + 1  # type: ignore[assignment]
            existing.updated_at = datetime.utcnow()  # type: ignore[assignment]
        else:
            preference = PetPreference(
                pet_id=pet_id,
                category=category,
                item_name=normalized_name,
                preference_type=preference_type,
                used_count=1,
            )
            db.add(preference)
        
        db.commit()
        logger.debug(f"Recorded preference for pet {pet_id}: {item_name}")
    
    except Exception as e:
        logger.error(f"Failed to record preference: {e}", exc_info=True)
        db.rollback()


def get_pet_top_preferences(db: Session, pet_id, category, limit: int = 5) -> list:
    """
    Return top saved preferences for a pet+category, ordered by usage.

    Result format:
    [
        {"name": "Nexgard", "used_count": 4},
        ...
    ]
    """
    rows = (
        db.query(PetPreference)
        .filter(
            PetPreference.pet_id == pet_id,
            PetPreference.category == category,
        )
        .order_by(PetPreference.used_count.desc(), PetPreference.updated_at.desc())
        .limit(limit)
        .all()
    )

    results = []
    for row in rows:
        name = str(getattr(row, "item_name", "")).strip()
        if not name:
            continue
        results.append({
            "name": name,
            "used_count": int(getattr(row, "used_count", 0) or 0),
        })
    return results
