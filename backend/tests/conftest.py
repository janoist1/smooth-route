"""Shared fixtures for auth tests: in-memory users DB and a fake verifier.

The suite must stay independent of the developer's .env (AUTH_MODE may be
'disabled' locally), so every auth test pins AUTH_MODE explicitly.
"""
from typing import Any, Optional

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core import auth
from app.core.config import settings
from app.models.models import User


class FakeVerifier:
    """Token verifier stub: token string -> canned claims, or raises."""

    def __init__(self, claims_by_token: Optional[dict[str, dict[str, Any]]] = None):
        self.claims_by_token = claims_by_token or {}

    def verify(self, token: str) -> dict[str, Any]:
        if token not in self.claims_by_token:
            raise auth.TokenVerificationError("Invalid token: unknown")
        return self.claims_by_token[token]


@pytest.fixture
def users_session_factory():
    """SQLite session factory with only the users table (no PostGIS needed).

    StaticPool + check_same_thread=False: TestClient drives the app from a
    worker thread, and the in-memory DB must be shared across threads.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    User.__table__.create(engine)
    factory = sessionmaker(bind=engine)
    yield factory
    engine.dispose()


@pytest.fixture
def clerk_mode(monkeypatch):
    """Force AUTH_MODE=clerk regardless of the local .env."""
    monkeypatch.setattr(settings, "AUTH_MODE", "clerk")


@pytest.fixture
def fake_verifier():
    """Install a FakeVerifier for the test and restore afterwards."""
    verifier = FakeVerifier()
    auth.set_token_verifier(verifier)
    yield verifier
    auth.set_token_verifier(None)
