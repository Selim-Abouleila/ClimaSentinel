"""
Pydantic schemas for request / response validation.
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# ── Request ──────────────────────────────────────────────────────────────

class PredictionRequest(BaseModel):
    """Incoming prediction request from the frontend."""
    city: str = Field(
        ...,
        description="City name (must be one of the 10 tracked cities)",
        examples=["Paris"],
    )
    date: Optional[str] = Field(
        None,
        description="Target date for prediction (YYYY-MM-DD). Defaults to tomorrow.",
        examples=["2026-06-20"],
    )


# ── Response ─────────────────────────────────────────────────────────────

class PredictionResponse(BaseModel):
    """Prediction result returned to the frontend."""
    city: str
    date: str
    temperature_celsius: float = Field(..., description="Predicted temperature (°C)")
    air_quality_index: float = Field(..., description="Predicted AQI (0-500)")
    air_quality_label: str = Field(..., description="AQI category (Good, Moderate, ...)")
    flood_risk: str = Field(..., description="Flood risk level (Low, Medium, High)")
    confidence: float = Field(..., description="Model confidence (0-1)")
    model_version: str = Field(..., description="MLflow model version used")
    prediction_timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="When the prediction was made",
    )


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = "healthy"
    environment: str
    model_loaded: bool
    model_version: Optional[str] = None
    uptime_seconds: float


class ErrorResponse(BaseModel):
    """Standard error response."""
    error: str
    detail: Optional[str] = None
