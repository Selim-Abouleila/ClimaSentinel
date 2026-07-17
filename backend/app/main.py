"""
ClimaSentinel — FastAPI Backend

Endpoints:
  GET  /        → welcome message
  GET  /health  → health check
"""

import logging
import os
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import numpy as np
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from google.cloud import bigquery

from prometheus_fastapi_instrumentator import Instrumentator

from .config import get_settings
from .ml_pipeline import (
    ModelCompatibilityError,
    predict_with_ensemble_spread,
    validate_fitted_pipeline,
)

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s")

# ── Track uptime ─────────────────────────────────────────────────────────
_start_time: float = 0.0

# ── Cached ML Model (loaded once at first request) ──────────────────────
MODEL_NAME = "ClimaSentinel_RiskForecaster"
SUB_SCORE_NAMES = (
    "heat_score",
    "wind_score",
    "rain_score",
    "air_score",
    "river_score",
)


@dataclass(frozen=True)
class LoadedModel:
    estimator: Any
    prediction_source: str
    model_version: str | None


_cached_model: LoadedModel | None = None


def _latest_registered_model_version() -> str:
    """Resolve the same latest registry policy to a concrete version string."""
    from mlflow.tracking import MlflowClient

    versions = list(
        MlflowClient().search_model_versions(f"name='{MODEL_NAME}'")
    )
    ready_versions = [
        version for version in versions if getattr(version, "status", None) == "READY"
    ]
    if not ready_versions:
        raise ModelCompatibilityError(
            f"No ready registered versions are available for {MODEL_NAME}"
        )
    return str(
        max(ready_versions, key=lambda version: int(version.version)).version
    )

def _get_ml_model():
    """Load and cache the ML model. Downloads once, reuses forever."""
    global _cached_model
    if _cached_model is not None:
        return _cached_model
    
    import joblib
    
    # Try local pickle first
    model_path = os.path.join(os.path.dirname(__file__), "risk_forecaster.pkl")
    if os.path.exists(model_path):
        try:
            estimator = joblib.load(model_path)
            validate_fitted_pipeline(estimator)
            _cached_model = LoadedModel(
                estimator=estimator,
                prediction_source="local_artifact",
                model_version="local",
            )
            log.info("Compatible ML model loaded from local pickle artifact.")
            return _cached_model
        except Exception:
            log.warning(
                "Local model artifact is unavailable or incompatible; trying MLflow.",
                exc_info=True,
            )
    
    # Try MLflow/DagsHub registry
    try:
        if os.environ.get("DAGSHUB_USER_TOKEN"):
            import dagshub
            dagshub.init(repo_owner=os.environ.get("DAGSHUB_USERNAME", "Selim-Abouleila"), repo_name="ClimaSentinel", mlflow=True)
        import mlflow.sklearn
        model_version = _latest_registered_model_version()
        estimator = mlflow.sklearn.load_model(
            f"models:/{MODEL_NAME}/{model_version}"
        )
        validate_fitted_pipeline(estimator)
        _cached_model = LoadedModel(
            estimator=estimator,
            prediction_source="mlflow_registry",
            model_version=model_version,
        )
        log.info(
            "Compatible ML model version %s loaded from MLflow and cached.",
            model_version,
        )
        return _cached_model
    except Exception:
        log.warning(
            "No compatible MLflow registry model is available.",
            exc_info=True,
        )
        return None


def _is_production() -> bool:
    return settings.ENVIRONMENT.strip().lower() == "production"


def _heuristic_predictions(row: dict[str, Any], horizon_days: int):
    """Return the existing temporary non-production fallback and its spread."""
    base = float(
        row.get("real_current_tipping_score")
        or row.get("current_tipping_score")
        or 50.0
    )
    t_max = float(row.get(f"temp_forecast_plus_{horizon_days}d") or 25.0)
    p_sum = float(row.get(f"precip_forecast_plus_{horizon_days}d") or 0.0)
    w_max = float(row.get(f"wind_forecast_plus_{horizon_days}d") or 20.0)
    river_disc = float(row.get("river_discharge_m3s") or 0.0)

    scores = np.asarray(
        [
            min(100.0, max(0.0, base * 0.4 + (t_max - 20.0) * 2.5)),
            min(
                100.0,
                max(0.0, (w_max - 30.0) * 2.0 if w_max > 30 else base * 0.2),
            ),
            min(100.0, max(0.0, p_sum * 5.0 if p_sum > 0 else base * 0.2)),
            min(100.0, max(0.0, base * 0.8)),
            min(100.0, max(0.0, base * 0.5 if river_disc > 0 else 0.0)),
        ],
        dtype=float,
    )
    standard_deviations = np.where(scores > 0, scores * 0.12, 0.0)
    return scores, standard_deviations


def _build_forecast_statistics(predictions, standard_deviations):
    """Apply the existing interval formula to five validated sub-scores."""
    predictions = np.asarray(predictions, dtype=float)
    standard_deviations = np.asarray(standard_deviations, dtype=float)
    expected_shape = (len(SUB_SCORE_NAMES),)
    if predictions.shape != expected_shape or standard_deviations.shape != expected_shape:
        raise ModelCompatibilityError(
            "Forecast prediction and spread must each contain exactly five values"
        )
    if not np.isfinite(predictions).all() or not np.isfinite(standard_deviations).all():
        raise ModelCompatibilityError("Forecast prediction and spread must be finite")

    clipped_predictions = np.clip(predictions, 0.0, 100.0)
    confidence_intervals = {}
    for index, name in enumerate(SUB_SCORE_NAMES):
        mean_value = clipped_predictions[index]
        margin = 1.96 * standard_deviations[index]
        confidence_intervals[name] = {
            "estimated_score": round(float(mean_value), 1),
            "ci_lower": round(float(max(0.0, mean_value - margin)), 1),
            "ci_upper": round(float(min(100.0, mean_value + margin)), 1),
            "confidence_margin": round(float(margin), 1),
        }

    driver_index = int(np.argmax(clipped_predictions))
    total_estimated = round(float(clipped_predictions[driver_index]), 1)
    total_margin = round(float(1.96 * standard_deviations[driver_index]), 1)
    return confidence_intervals, total_estimated, total_margin


# ── Lifespan (startup / shutdown) ────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _start_time
    _start_time = time.time()

    settings = get_settings()
    log.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION} [{settings.ENVIRONMENT}]")
    yield
    log.info("Shutting down.")


# ── App ──────────────────────────────────────────────────────────────────
settings = get_settings()

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="ClimaSentinel API",
    lifespan=lifespan,
)

# CORS — allow the frontend to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # tighten in production via env var
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Prometheus Monitoring ────────────────────────────────────────────────
# Auto-instruments all routes and exposes GET /metrics
Instrumentator().instrument(app).expose(app)


# ── Routes ───────────────────────────────────────────────────────────────

@app.get("/", tags=["General"])
def root():
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
    }


@app.get("/health", tags=["General"])
def health():
    return {
        "status": "healthy",
        "environment": settings.ENVIRONMENT,
        "uptime_seconds": round(time.time() - _start_time, 2),
    }


# ── BigQuery Data Endpoints ──────────────────────────────────────────────
from .db import get_bq_client

@app.get("/data/current-scores", tags=["Data"])
def get_current_scores(limit: int = 10):
    """
    Example endpoint showing how to connect to BigQuery and query the 
    `mart_city_score_current` table from your dbt_marts dataset.
    """
    try:
        client = get_bq_client()
        # Querying the current scores mart as an example
        query = f"""
            SELECT city_id, current_tipping_score, current_primary_driver, rank
            FROM `{settings.GCP_PROJECT_ID}.{settings.BQ_DATASET}.mart_city_score_current`
            ORDER BY current_tipping_score DESC
            LIMIT @limit
        """
        
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("limit", "INT64", limit)
            ]
        )
        
        query_job = client.query(query, job_config=job_config)
        results = query_job.result()
        
        return [dict(row) for row in results]
    except Exception as e:
        log.error(f"Error querying BigQuery: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve data from BigQuery")


@app.get("/data/history-scores", tags=["Data"])
def get_history_scores(city_id: str = None, limit: int = 50):
    """
    Returns historical tipping scores from `mart_city_score_history`.
    """
    try:
        client = get_bq_client()
        query = f"SELECT * FROM `{settings.GCP_PROJECT_ID}.{settings.BQ_DATASET}.mart_city_score_history`"
        query_parameters = [bigquery.ScalarQueryParameter("limit", "INT64", limit)]
        if city_id:
            query += " WHERE city_id = @city_id"
            query_parameters.append(bigquery.ScalarQueryParameter("city_id", "STRING", city_id))
        query += " ORDER BY prediction_date DESC LIMIT @limit"
        job_config = bigquery.QueryJobConfig(query_parameters=query_parameters)
        query_job = client.query(query, job_config=job_config)
        results = query_job.result()
        return [dict(row) for row in results]
    except Exception as e:
        log.error(f"Error querying BigQuery history: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve history data")


@app.get("/data/current-zones", tags=["Data"])
def get_current_zones(limit: int = 20):
    """
    Returns current tipping zones from `mart_city_zone_current`.
    """
    try:
        client = get_bq_client()
        query = f"SELECT * FROM `{settings.GCP_PROJECT_ID}.{settings.BQ_DATASET}.mart_city_zone_current` LIMIT @limit"
        job_config = bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter("limit", "INT64", limit)])
        query_job = client.query(query, job_config=job_config)
        results = query_job.result()
        return [dict(row) for row in results]
    except Exception as e:
        log.error(f"Error querying BigQuery zones: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve zones data")


@app.get("/data/city/{city_id}/scores", tags=["Data"])
def get_city_scores(city_id: str):
    """
    Returns the individual tipping sub-scores (heat, wind, rain, air, river)
    for a single city within the current 48-hour operational window.

    Source table : mart_city_score_detail  (new mart — does NOT touch
                   mart_city_score_current or mart_city_score_history).

    Returns 404 if the city_id is not found in the mart.
    """
    try:
        client = get_bq_client()
        query = f"""
            SELECT
                city_id,
                current_tipping_score,
                current_primary_driver,
                heat_score,
                wind_score,
                rain_score,
                air_score,
                river_score
            FROM `{settings.GCP_PROJECT_ID}.{settings.BQ_DATASET}.mart_city_score_detail`
            WHERE city_id = @city_id
            LIMIT 1
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("city_id", "STRING", city_id)
            ]
        )
        query_job = client.query(query, job_config=job_config)
        rows = list(query_job.result())

        if not rows:
            raise HTTPException(
                status_code=404,
                detail=f"City '{city_id}' not found in mart_city_score_detail"
            )

        return dict(rows[0])

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Error querying city scores for '{city_id}': {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve city scores")


@app.get("/data/city/{city_id}/forecast", tags=["Data"])
def get_city_forecast(
    city_id: str,
    horizon_days: int = Query(default=3, ge=1, le=3, description="Forecast horizon in days (1-3)")
):
    """
    Returns the N-day future climate tipping forecast for a single city.
    Accepts horizon_days (1-3) to control how far ahead the model predicts.
    Fetches the pre-computed weather trajectory from `mart_ml_feature_store`,
    runs inference via the Multi-Output Random Forest model, and calculates
    individual sub-scores, total tipping risk, and 95% confidence intervals.
    """
    try:
        client = get_bq_client()
        query = f"""
            SELECT 
                m.*, 
                c.current_tipping_score AS real_current_tipping_score,
                c.current_primary_driver AS real_primary_driver
            FROM `{settings.GCP_PROJECT_ID}.{settings.BQ_DATASET}.mart_ml_feature_store` m
            INNER JOIN `{settings.GCP_PROJECT_ID}.{settings.BQ_DATASET}.mart_city_score_current` c
                ON m.city_id = c.city_id
            WHERE m.city_id = @city_id
              AND m.date = CURRENT_DATE('UTC')
              AND m.temp_forecast_plus_3d IS NOT NULL
            ORDER BY m.date DESC
            LIMIT 1
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("city_id", "STRING", city_id)
            ]
        )
        query_job = client.query(query, job_config=job_config)
        rows = list(query_job.result())

        if not rows:
            raise HTTPException(
                status_code=404,
                detail=f"City '{city_id}' not found in mart_ml_feature_store"
            )

        row = dict(rows[0])
        
        # ── ML Model Inference & Confidence Intervals ──
        feature_row = dict(row)
        feature_row["current_tipping_score"] = row["real_current_tipping_score"]
        
        # ── Forward-fill forecast features beyond the requested horizon ──
        # Preserve the existing shorter-horizon behavior for temperature,
        # precipitation, and average-wind features through Day +3.
        if horizon_days < 3:
            for prefix in ['temp_forecast_plus_', 'precip_forecast_plus_', 'wind_forecast_plus_']:
                for d in range(horizon_days + 1, 4):  # e.g. horizon=1 → fill 2d,3d with 1d
                    col = f"{prefix}{d}d"
                    prev_col = f"{prefix}{horizon_days}d"
                    if col in feature_row and prev_col in feature_row:
                        feature_row[col] = feature_row[prev_col]

        try:
            loaded_model = _get_ml_model()
            if loaded_model is None:
                raise ModelCompatibilityError("No compatible ML model could be loaded")

            all_predictions, all_standard_deviations = predict_with_ensemble_spread(
                loaded_model.estimator,
                feature_row,
            )
            predictions = all_predictions[0]
            standard_deviations = all_standard_deviations[0]
            prediction_source = loaded_model.prediction_source
            model_version = loaded_model.model_version
            conf_intervals, total_estimated, total_margin = (
                _build_forecast_statistics(predictions, standard_deviations)
            )
        except Exception:
            if _is_production():
                log.error(
                    "ML forecast failed in production for city '%s'.",
                    city_id,
                    exc_info=True,
                )
                raise HTTPException(
                    status_code=503,
                    detail="ML forecast model is temporarily unavailable",
                )

            log.warning(
                "ML forecast failed for city '%s'; using the explicit "
                "non-production heuristic fallback.",
                city_id,
                exc_info=True,
            )
            predictions, standard_deviations = _heuristic_predictions(
                row,
                horizon_days,
            )
            prediction_source = "heuristic_fallback"
            model_version = None
            conf_intervals, total_estimated, total_margin = (
                _build_forecast_statistics(predictions, standard_deviations)
            )

        driver_map = {0: 'Heat', 1: 'Wind', 2: 'Rain', 3: 'Air Quality', 4: 'River/Flood'}
        best_driver = driver_map[np.argmax([conf_intervals[n]["estimated_score"] for n in SUB_SCORE_NAMES])]

        # ── Build weather trajectory for the selected horizon ──
        weather_trajectory = {}
        for d in range(1, horizon_days + 1):
            weather_trajectory[f"temp_max_plus_{d}d"] = float(row.get(f'temp_forecast_plus_{d}d') or 0.0)
        # Include precip and wind for the target day
        weather_trajectory[f"precip_plus_{horizon_days}d"] = float(row.get(f'precip_forecast_plus_{horizon_days}d') or 0.0)
        weather_trajectory[f"wind_plus_{horizon_days}d"] = float(row.get(f'wind_forecast_plus_{horizon_days}d') or 0.0)

        return {
            "city_id": city_id,
            "horizon_days": horizon_days,
            "prediction_date": str(row['date']),
            "current_tipping_score": round(float(row.get('real_current_tipping_score') or row.get('current_tipping_score') or 0.0), 1),
            "estimated_total_tipping_score": total_estimated,
            "total_confidence_margin": total_margin,
            "total_ci_lower": round(float(max(0.0, total_estimated - total_margin)), 1),
            "total_ci_upper": round(float(min(100.0, total_estimated + total_margin)), 1),
            "forecast_primary_driver": best_driver,
            "sub_scores_forecast": conf_intervals,
            "weather_trajectory": weather_trajectory,
            "prediction_source": prediction_source,
            "model_version": model_version,
        }

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Error querying forecast for '{city_id}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve forecast data: {e}")
