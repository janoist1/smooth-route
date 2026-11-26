"""Responses over 1 KB are gzip-compressed (roadSegments answers are ~350 KB)."""
from fastapi.testclient import TestClient


def _client(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "RUN_MIGRATIONS_ON_STARTUP", False)
    from app.main import app

    return TestClient(app)


def test_large_graphql_response_is_gzipped(monkeypatch):
    client = _client(monkeypatch)
    # Introspection (local full schema) is large and needs no database.
    resp = client.post(
        "/graphql",
        json={"query": "{ __schema { types { name description } } }"},
        headers={"accept-encoding": "gzip"},
    )
    assert resp.status_code == 200
    assert resp.headers.get("content-encoding") == "gzip"
    assert "__schema" in resp.json()["data"]  # httpx decompresses transparently


def test_small_response_is_not_compressed(monkeypatch):
    client = _client(monkeypatch)
    resp = client.get("/health", headers={"accept-encoding": "gzip"})
    assert resp.status_code == 200
    assert "content-encoding" not in resp.headers
