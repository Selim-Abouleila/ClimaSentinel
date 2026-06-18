"""
Starter tests for the ClimaSentinel backend.
These run automatically in CI on every PR → dev.
"""

import pytest
from unittest.mock import patch, MagicMock
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
def test_openapi_schema_generation():
    """Ensure OpenAPI schema generates successfully."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert "info" in schema
    assert schema["info"]["title"] == "ClimaSentinel Backend"

# ── Mock Data Tests ──────────────────────────────────────────────────────

@patch("app.db.bigquery.Client")
def test_get_current_scores_mocked(mock_bq_client):
    """
    Test the /data/current-scores endpoint with a mocked BigQuery client.
    """
    # Create a mock query job and result
    mock_query_job = MagicMock()
    mock_query_job.result.return_value = [
        {"city_id": "Paris", "current_tipping_score": 85.5},
        {"city_id": "London", "current_tipping_score": 72.1}
    ]
    
    # Configure the mock client to return our mock query job
    mock_client_instance = MagicMock()
    mock_client_instance.query.return_value = mock_query_job
    
    # Set the get_bq_client patch to return our mock client instance
    with patch("app.main.get_bq_client", return_value=mock_client_instance):
        response = client.get("/data/current-scores?limit=2")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["city_id"] == "Paris"
        assert data[0]["current_tipping_score"] == 85.5
