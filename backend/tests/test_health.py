"""
Starter tests for the ClimaSentinel backend.
These run automatically in CI on every PR → dev.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


# ── Unit Tests ───────────────────────────────────────────────────────────

def test_root_returns_service_info():
    """GET / should return service name and version."""
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert "service" in body
    assert "version" in body
    assert body["service"] == "ClimaSentinel API"


def test_health_returns_healthy():
    """GET /health should return status healthy."""
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"


def test_health_contains_uptime():
    """GET /health should include uptime_seconds >= 0."""
    resp = client.get("/health")
    body = resp.json()
    assert "uptime_seconds" in body
    assert body["uptime_seconds"] >= 0


# ── Integration Tests ────────────────────────────────────────────────────

@pytest.mark.integration
def test_cors_headers_present():
    """Responses should include CORS headers for cross-origin requests."""
    resp = client.get("/", headers={"Origin": "http://localhost:3000"})
    assert resp.status_code == 200
    assert "access-control-allow-origin" in resp.headers


@pytest.mark.integration
def test_openapi_schema_available():
    """The OpenAPI schema at /openapi.json should be valid JSON."""
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    schema = resp.json()
    assert "openapi" in schema
    assert "paths" in schema
