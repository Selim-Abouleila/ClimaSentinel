"""
Model loading and prediction service.

Loads the ML model from the MLflow registry (DagsHub).
Falls back to a dummy model when MLflow is not configured yet,
so development and CI can proceed without a trained model.
"""

import logging
import numpy as np
from datetime import datetime, timedelta
from typing import Optional

from .config import get_settings
from .schemas import PredictionResponse

log = logging.getLogger(__name__)

# ── Valid cities (must match config/cities.csv) ──────────────────────────
VALID_CITIES = [
    "Paris", "London", "Madrid", "Berlin", "Rome",
    "Amsterdam", "Athens", "Warsaw", "Lisbon", "Stockholm",
]

# ── Module-level model state ─────────────────────────────────────────────
_model = None
_model_version: Optional[str] = None


def load_model() -> None:
    """
    Load the production model from MLflow registry.
    Falls back to a dummy model if MLflow is not configured.
    """
    global _model, _model_version
    settings = get_settings()

    if not settings.MLFLOW_TRACKING_URI:
        log.warning(
            "MLFLOW_TRACKING_URI not set — using dummy model. "
            "Set it to load a real model from the registry."
        )
        _model = "dummy"
        _model_version = "dummy-v0"
        return

    try:
        import mlflow

        mlflow.set_tracking_uri(settings.MLFLOW_TRACKING_URI)
        model_uri = f"models:/{settings.MLFLOW_MODEL_NAME}/{settings.MLFLOW_MODEL_STAGE}"
        log.info(f"Loading model from: {model_uri}")

        _model = mlflow.pyfunc.load_model(model_uri)

        # Try to get version info
        client = mlflow.tracking.MlflowClient()
        versions = client.get_latest_versions(
            settings.MLFLOW_MODEL_NAME,
            stages=[settings.MLFLOW_MODEL_STAGE],
        )
        _model_version = versions[0].version if versions else "unknown"
        log.info(f"Model loaded successfully — version {_model_version}")

    except Exception as exc:
        log.error(f"Failed to load model from MLflow: {exc}")
        log.warning("Falling back to dummy model.")
        _model = "dummy"
        _model_version = "dummy-v0"


def is_model_loaded() -> bool:
    return _model is not None


def get_model_version() -> Optional[str]:
    return _model_version


def predict(city: str, date: Optional[str] = None) -> PredictionResponse:
    """
    Run prediction for a given city and date.
    """
    if city not in VALID_CITIES:
        raise ValueError(
            f"Unknown city '{city}'. Must be one of: {', '.join(VALID_CITIES)}"
        )

    # Default to tomorrow
    if date is None:
        target_date = (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        target_date = date

    if _model == "dummy" or _model is None:
        return _dummy_predict(city, target_date)

    # ── Real model prediction ────────────────────────────────────────
    # TODO: build feature vector from BigQuery data and pass to model
    # features = fetch_features_from_bigquery(city, target_date)
    # result = _model.predict(features)
    # For now, fall back to dummy until training pipeline is ready
    return _dummy_predict(city, target_date)


def _dummy_predict(city: str, date: str) -> PredictionResponse:
    """
    Deterministic dummy predictions for development/testing.
    Uses city name hash so results are consistent per city.
    """
    seed = hash(city + date) % 2**32
    rng = np.random.RandomState(seed)

    temp = round(rng.uniform(5.0, 38.0), 1)
    aqi = round(rng.uniform(10.0, 200.0), 1)

    if aqi < 50:
        aqi_label = "Good"
    elif aqi < 100:
        aqi_label = "Moderate"
    elif aqi < 150:
        aqi_label = "Unhealthy for Sensitive Groups"
    else:
        aqi_label = "Unhealthy"

    flood_risk_val = rng.random()
    if flood_risk_val < 0.6:
        flood_risk = "Low"
    elif flood_risk_val < 0.85:
        flood_risk = "Medium"
    else:
        flood_risk = "High"

    return PredictionResponse(
        city=city,
        date=date,
        temperature_celsius=temp,
        air_quality_index=aqi,
        air_quality_label=aqi_label,
        flood_risk=flood_risk,
        confidence=round(rng.uniform(0.65, 0.95), 2),
        model_version=_model_version or "dummy-v0",
    )
