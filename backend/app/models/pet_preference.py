"""
PetCircle — Pet Preference Model

Tracks items that users have ordered for their pets, both from
recommended lists and custom orders. Used to remember user preferences
and make future recommendations more personalized.

Workflow:
1. When a user orders an item (whether from recommendation or custom), 
   record it as a preference.
2. Preferences are indexed by category and pet_id for quick lookup.
3. Used during recommendation UI to show user's historical orders.

Constraints:
    - pet_id: FK to pets(id), ON DELETE CASCADE
    - category: medicines, food_nutrition, supplements
    - preference_type: "recommendation" (from AI list) or "custom" (user typed)
    - item_name: the item name (extracted from order or recommendation)
    - used_count: how many times user ordered this item
"""

import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base


class PetPreference(Base):
    """
    Tracks items a user has ordered for a pet.
    
    Stores both:
    - Items from recommendation lists (preference_type="recommendation")
    - Custom items user typed (preference_type="custom")
    
    Used to:
    - Remember user's past orders
    - Personalize future recommendations
    - Show "frequently ordered" items
    """

    __tablename__ = "pet_preferences"

    # Primary key — UUID
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Reference to the pet
    # ON DELETE CASCADE — if pet deleted, preferences removed
    pet_id = Column(
        UUID(as_uuid=True),
        ForeignKey("pets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Category: medicines, food_nutrition, supplements
    category = Column(String(30), nullable=False)

    # Preference type: "recommendation" or "custom"
    # - "recommendation": item came from AI recommendation list
    # - "custom": user typed their own item
    preference_type = Column(String(20), nullable=False, default="custom")

    # The item name as ordered by user
    # For recommendations, this is the item name from the recommendation.
    # For custom, this is what the user typed.
    item_name = Column(String(500), nullable=False)

    # How many times user has ordered this item
    # Incremented each time user orders it
    used_count = Column(Integer, nullable=False, default=1)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # --- Indexes ---
    # Speed up lookups for showing user preferences in UI
    __table_args__ = (
        Index("ix_pet_preferences_pet_category", "pet_id", "category"),
        Index("ix_pet_preferences_preference_type", "preference_type"),
    )

    # --- Relationships ---
    pet = relationship("Pet", foreign_keys=[pet_id])
