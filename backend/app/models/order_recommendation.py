"""
PetCircle — Order Recommendation Model

Caches AI-generated product recommendations for pet profiles.
Recommendations are generated based on breed, species, and age range.

Workflow:
1. When a user orders, we check if a recommendation exists for their pet's profile.
2. If not found, we call the AI recommendation service to generate suggestions.
3. Store the recommendation in DB to avoid regenerating for similar pets.
4. User selects items and we track their preferences.

Constraints:
    - pet_id: FK to pets(id), ON DELETE CASCADE
    - category: medicines, food_nutrition, supplements
    - species: "dog" or "cat"
    - breed: optional, may be None for breed-agnostic recommendations
    - age_range: optional age range (e.g., "0-2" for puppies)
    - items: JSON array of recommended items with descriptions
    - used_count: tracks how many users have used this recommendation
"""

import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.database import Base


class OrderRecommendation(Base):
    """
    Caches AI-generated recommendations for pet profiles.
    
    A recommendation is uniquely identified by:
    - species (dog/cat)
    - breed (may be None for breed-agnostic)
    - age_range (optional)
    - category (medicines/food_nutrition/supplements)
    
    Once generated, the same recommendation can be reused for multiple
    users with similar pet profiles, reducing API calls.
    """

    __tablename__ = "order_recommendations"

    # Primary key — UUID
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Reference to the first pet that triggered this recommendation
    # Optional (ON DELETE CASCADE) — for tracking origin
    pet_id = Column(
        UUID(as_uuid=True),
        ForeignKey("pets.id", ondelete="CASCADE"),
        nullable=True,
    )

    # Species: dog or cat
    species = Column(String(10), nullable=False)

    # Breed: optional, may be None for breed-agnostic recommendations
    breed = Column(String(100), nullable=True)

    # Age range as text (e.g., "0-2", "2-7", "7+")
    # Helps tailor recommendations for life stages
    age_range = Column(String(20), nullable=True)

    # Category: medicines, food_nutrition, supplements
    category = Column(String(30), nullable=False)

    # JSON array of recommended items
    # Format: [
    #   {
    #     "name": "Product Name",
    #     "description": "Brief description",
    #     "reason": "Why recommended (e.g., 'Essential for puppies')"
    #   },
    #   ...
    # ]
    items = Column(JSONB, nullable=False, default=list)

    # Tracks how many times this recommendation was used
    # Helps identify popular recommendations
    used_count = Column(Integer, nullable=False, default=0)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # --- Indexes ---
    # Speed up lookups by species, breed, age_range, category
    __table_args__ = (
        Index("ix_order_recommendations_species", "species"),
        Index("ix_order_recommendations_breed", "breed"),
        Index("ix_order_recommendations_category", "category"),
        Index(
            "ix_order_recommendations_profile",
            "species",
            "breed",
            "age_range",
            "category",
        ),
    )

    # --- Relationships ---
    pet = relationship("Pet", foreign_keys=[pet_id])
