"""
Diagnostic test result model for blood/urine dashboard values.
"""

import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Date, ForeignKey, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base


class DiagnosticTestResult(Base):
    __tablename__ = "diagnostic_test_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pet_id = Column(UUID(as_uuid=True), ForeignKey("pets.id", ondelete="CASCADE"), index=True, nullable=False)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), index=True, nullable=True)

    test_type = Column(String(30), nullable=False)  # blood | urine
    parameter_name = Column(String(120), nullable=False)
    value_numeric = Column(Numeric(14, 4), nullable=True)
    value_text = Column(String(200), nullable=True)
    unit = Column(String(60), nullable=True)
    reference_range = Column(String(120), nullable=True)
    status_flag = Column(String(20), nullable=True)  # low | normal | high | abnormal
    observed_at = Column(Date, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    pet = relationship("Pet")
    document = relationship("Document")
