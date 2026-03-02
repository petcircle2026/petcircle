"""
PetCircle — Shared Test Fixtures

Sets APP_ENV=test before any imports so config.py loads test env vars.
"""

import os

# Must be set before importing app modules.
os.environ["APP_ENV"] = "test"

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def app():
    """Create the FastAPI application for testing."""
    from app.main import app as _app
    return _app


@pytest.fixture(scope="session")
def client(app):
    """Provide a test HTTP client."""
    return TestClient(app)
