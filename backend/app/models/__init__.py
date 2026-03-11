"""
PetCircle Phase 1 — SQLAlchemy Models Package

All models are imported here to ensure they are registered with
SQLAlchemy's declarative base. This is required for relationship
resolution and for alembic/migration tooling to discover all tables.
"""

from app.models.user import User
from app.models.pet import Pet
from app.models.preventive_master import PreventiveMaster
from app.models.preventive_record import PreventiveRecord
from app.models.reminder import Reminder
from app.models.document import Document
from app.models.message_log import MessageLog
from app.models.dashboard_token import DashboardToken
from app.models.conflict_flag import ConflictFlag
from app.models.shown_fun_fact import ShownFunFact
from app.models.diagnostic_test_result import DiagnosticTestResult
from app.models.order import Order
from app.models.order_recommendation import OrderRecommendation
from app.models.pet_preference import PetPreference

__all__ = [
    "User",
    "Pet",
    "PreventiveMaster",
    "PreventiveRecord",
    "Reminder",
    "Document",
    "MessageLog",
    "DashboardToken",
    "ConflictFlag",
    "ShownFunFact",
    "DiagnosticTestResult",
    "Order",
    "OrderRecommendation",
    "PetPreference",
]
