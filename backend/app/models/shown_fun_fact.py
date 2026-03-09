"""
PetCircle Phase 1 — Shown Fun Fact Model

Tracks which breed fun facts a user has already seen, so that
acknowledgment messages never repeat the same fact until all
available facts have been shown.

Design:
    - fact_hash: SHA-256 hex digest of the fact text (64 chars).
      Using a hash instead of storing the full text keeps the table lean.
    - Unique constraint on (user_id, fact_hash) prevents duplicate entries.
    - CASCADE delete: when a user is removed, their shown facts are cleaned up.
"""

import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class ShownFunFact(Base):
    """Records a single fun fact that has been shown to a user."""

    __tablename__ = "shown_fun_facts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    fact_hash = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
