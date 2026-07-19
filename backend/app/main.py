"""
ClimaSentinel — FastAPI Backend

Endpoints:
  GET  /        → welcome message
  GET  /health  → health check
"""

import logging
import math
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
from .forecast_rules import forecast_rule_estimates
from .ml_pipeline import (
    FEATURE_SCHEMA_VERSION,
    REGISTERED_MODEL_NAME,
    RULE_BASED_SCORE_NAMES,
    TARGET_SCORE_NAMES,
    ModelCompatibilityError,
    predict_with_ensemble_spread,
    validate_fitted_pipeline,
)
from .schemas import CityForecastResponse

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s")

# ── Track uptime ─────────────────────────────────────────────────────────
_start_time: float = 0.0

# ── Cached ML Model (loaded once at first request) ──────────────────────
MODEL_NAME = REGISTERED_MODEL_NAME
SUB_SCORE_NAMES = (
    "heat_score",
    "wind_score",
    "rain_score",
    "air_score",
    "river_score",
)

LEARNED_SUB_SCORE_NAMES = tuple(f"{name}_score" for name in TARGET_SCORE_NAMES)
DRIVER_LABELS = {
    "heat_score": "Heat",
    "wind_score": "Wind",
    "rain_score": "Rain",
    "air_score": "Air Quality",
    "river_score": "River/Flood",
}


@dataclass(frozen=True)
class LoadedModel:
    estimator: Any
    prediction_source: str
    model_version: str | None


@dataclass(frozen=True)
class ResolvedModelReference:
    model_uri: str
    model_version: str
    model_alias: str | None


_cached_model: LoadedModel | None = None


def _validate_ready_model_version(model_version, selection: str) -> str:
    """Return a concrete ready version or reject the selected reference."""
    version = str(getattr(model_version, "version", "")).strip()
    status = str(getattr(model_version, "status", "")).strip().upper()
    if not version or not version.isdigit() or int(version) <= 0:
        raise ModelCompatibilityError(
            f"{selection} did not resolve to a valid registered model version"
        )
    if status != "READY":
        raise ModelCompatibilityError(
            f"{selection} resolved to model version {version}, which is not ready"
        )
    return str(int(version))


def _resolve_registry_model_reference(client) -> ResolvedModelReference:
    """Resolve an explicit pin or registry alias to one exact ready version."""
    configured_version = (settings.MLFLOW_MODEL_VERSION or "").strip()
    if configured_version:
        if not configured_version.isdigit() or int(configured_version) <= 0:
            raise ModelCompatibilityError(
                "MLFLOW_MODEL_VERSION must be a positive integer string"
            )
        normalized_version = str(int(configured_version))
        try:
            model_version = client.get_model_version(
                MODEL_NAME,
                normalized_version,
            )
        except Exception as exc:
            raise ModelCompatibilityError(
                f"Configured model version {normalized_version} could not be resolved"
            ) from exc
        resolved_version = _validate_ready_model_version(
            model_version,
            f"Configured model version {normalized_version}",
        )
        return ResolvedModelReference(
            model_uri=f"models:/{MODEL_NAME}/{resolved_version}",
            model_version=resolved_version,
            model_alias=None,
        )

    model_alias = (settings.MLFLOW_MODEL_ALIAS or "").strip() or "champion"
    try:
        model_version = client.get_model_version_by_alias(
            MODEL_NAME,
            model_alias,
        )
    except Exception as exc:
        raise ModelCompatibilityError(
            f"Registry alias '{model_alias}' could not be resolved"
        ) from exc
    resolved_version = _validate_ready_model_version(
        model_version,
        f"Registry alias '{model_alias}'",
    )
    return ResolvedModelReference(
        model_uri=f"models:/{MODEL_NAME}/{resolved_version}",
        model_version=resolved_version,
        model_alias=model_alias,
    )


def _allow_local_artifact() -> bool:
    return _allow_development_fallback()


def _get_ml_model():
    """Load and cache the ML model. Downloads once, reuses forever."""
    global _cached_model
    if _cached_model is not None:
        return _cached_model
    
    import joblib
    
    # Local artifacts are an explicit local-development convenience only.
    model_path = os.path.join(os.path.dirname(__file__), "risk_forecaster.pkl")
    if _allow_local_artifact() and os.path.exists(model_path):
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
            dagshub.init(
                repo_owner=os.environ.get(
                    "DAGSHUB_USERNAME",
                    "Selim-Abouleila",
                ),
                repo_name="ClimaSentinel",
                mlflow=True,
            )
        import mlflow.sklearn
        from mlflow.tracking import MlflowClient

        model_reference = _resolve_registry_model_reference(MlflowClient())
        if model_reference.model_alias is not None:
            log.info(
                "Resolved registry alias '%s' to model version %s.",
                model_reference.model_alias,
                model_reference.model_version,
            )
        else:
            log.info(
                "Resolved explicit model version pin %s.",
                model_reference.model_version,
            )
        estimator = mlflow.sklearn.load_model(model_reference.model_uri)
        validate_fitted_pipeline(estimator)
        _cached_model = LoadedModel(
            estimator=estimator,
            prediction_source="mlflow_registry",
            model_version=model_reference.model_version,
        )
        log.info(
            "Loaded exact registered model version %s and cached it.",
            model_reference.model_version,
        )
        return _cached_model
    except Exception:
        log.warning(
            "No compatible MLflow registry model is available.",
            exc_info=True,
        )
        return None


def _environment_name() -> str:
    return settings.ENVIRONMENT.strip().lower()


def _is_deployed_environment() -> bool:
    return _environment_name() in {"staging", "production"}


def _allow_development_fallback() -> bool:
    return _environment_name() in {"development", "dev", "local", "test"}


def _finite_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric_value):
        return None
    return numeric_value


def _clip_score(value: float) -> float:
    return round(float(np.clip(value, 0.0, 100.0)), 1)


def _development_heat_rain_estimates(
    row: dict[str, Any],
    horizon_days: int,
) -> np.ndarray:
    """Return explicit local-only rule estimates for Heat and Rain.

    This path exists so a developer can render the page without registry
    credentials. It is intentionally disabled in staging and production and is
    never presented as an observation-validated model prediction.
    """
    temperature = _finite_float(
        row.get(f"temp_forecast_plus_{horizon_days}d")
    )
    next_temperature = _finite_float(
        row.get(f"temp_forecast_plus_{horizon_days + 1}d")
    )
    normal_temperature = _finite_float(row.get("normal_temperature_2m_max"))
    precipitation = _finite_float(
        row.get(f"precip_forecast_plus_{horizon_days}d")
    )
    if None in (
        temperature,
        next_temperature,
        normal_temperature,
        precipitation,
    ):
        raise ModelCompatibilityError(
            "Development fallback requires complete same-vintage Heat/Rain inputs"
        )

    heat_score = (
        (temperature - normal_temperature) * 5.0
        + max(0.0, next_temperature - temperature) * 5.0
    )
    rain_score = precipitation * 2.0
    return np.asarray([_clip_score(heat_score), _clip_score(rain_score)])


def _build_learned_components(
    predictions: Any,
    standard_deviations: Any,
) -> dict[str, dict[str, Any]]:
    """Build uncalibrated tree-spread bands for learned Heat/Rain outputs."""
    predictions = np.asarray(predictions, dtype=float)
    standard_deviations = np.asarray(standard_deviations, dtype=float)
    expected_shape = (len(LEARNED_SUB_SCORE_NAMES),)
    if (
        predictions.shape != expected_shape
        or standard_deviations.shape != expected_shape
    ):
        raise ModelCompatibilityError(
            "Forecast prediction and spread must each contain exactly two values"
        )
    if (
        not np.isfinite(predictions).all()
        or not np.isfinite(standard_deviations).all()
    ):
        raise ModelCompatibilityError("Forecast prediction and spread must be finite")

    components: dict[str, dict[str, Any]] = {}
    for index, name in enumerate(LEARNED_SUB_SCORE_NAMES):
        score = _clip_score(predictions[index])
        margin = round(float(1.96 * max(0.0, standard_deviations[index])), 1)
        components[name] = {
            "estimated_score": score,
            "ci_lower": round(max(0.0, score - margin), 1),
            "ci_upper": round(min(100.0, score + margin), 1),
            "confidence_margin": margin,
            "available": True,
            "method": "learned_model",
            "validation_status": "era5_realized_validated",
            "uncertainty_method": "tree_spread_not_calibrated",
            "unavailable_reason": None,
        }
    return components


def _build_development_components(
    predictions: Any,
) -> dict[str, dict[str, Any]]:
    """Build explicitly unvalidated local Heat/Rain fallback components."""
    predictions = np.asarray(predictions, dtype=float)
    if predictions.shape != (len(LEARNED_SUB_SCORE_NAMES),):
        raise ModelCompatibilityError(
            "Development fallback must contain exactly two values"
        )
    if not np.isfinite(predictions).all():
        raise ModelCompatibilityError("Development fallback values must be finite")

    return {
        name: {
            "estimated_score": _clip_score(predictions[index]),
            "ci_lower": None,
            "ci_upper": None,
            "confidence_margin": None,
            "available": True,
            "method": "development_fallback_rule",
            "validation_status": "not_observation_validated",
            "uncertainty_method": "none",
            "unavailable_reason": None,
        }
        for index, name in enumerate(LEARNED_SUB_SCORE_NAMES)
    }


def _build_rule_components(
    row: dict[str, Any],
    horizon_days: int,
) -> dict[str, dict[str, Any]]:
    estimates = forecast_rule_estimates(row, horizon_days)
    return {
        name: {
            "estimated_score": estimate.score,
            "ci_lower": None,
            "ci_upper": None,
            "confidence_margin": None,
            "available": estimate.available,
            "method": "forecast_rule",
            "validation_status": "not_observation_validated",
            "uncertainty_method": "none",
            "unavailable_reason": estimate.unavailable_reason,
        }
        for name, estimate in estimates.items()
    }


def _summarize_components(
    components: dict[str, dict[str, Any]],
) -> tuple[str, str, float, float | None, float | None, float | None, str]:
    available_components = {
        name: component
        for name, component in components.items()
        if component["available"] and component["estimated_score"] is not None
    }
    if not available_components:
        raise ModelCompatibilityError("Forecast produced no available components")

    driver_name, driver = max(
        available_components.items(),
        key=lambda item: float(item[1]["estimated_score"]),
    )
    total = float(driver["estimated_score"])
    return (
        DRIVER_LABELS[driver_name],
        driver["method"],
        total,
        driver["confidence_margin"],
        driver["ci_lower"],
        driver["ci_upper"],
        driver["uncertainty_method"],
    )


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


@app.get(
    "/data/city/{city_id}/forecast",
    tags=["Data"],
    response_model=CityForecastResponse,
)
def get_city_forecast(
    city_id: str,
    horizon_days: int = Query(default=3, ge=1, le=3, description="Forecast horizon in days (1-3)")
):
    """
    Return the hybrid Day +1, +2 or +3 forecast for one city.

    Heat and Rain come from an ERA5-realized-label model. Wind, Air Quality and
    River/Flood remain deterministic indicators calculated from the same exact
    forecast vintage. Missing optional sources remain unavailable rather than
    being reported as zero. Only learned components expose an uncalibrated
    tree-spread band.
    """
    try:
        client = get_bq_client()
        query = f"""
            SELECT *
            FROM `{settings.GCP_PROJECT_ID}.{settings.BQ_DATASET}.mart_ml_serving_features_current`
            WHERE city_id = @city_id
              AND forecast_age_days = 0
              AND is_canonical_daily_vintage
              AND has_expected_horizon_dates
              AND has_complete_weather_feature_window
            ORDER BY ingested_at_utc DESC, ingestion_run_id DESC
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
                detail=(
                    f"City '{city_id}' has no current complete point-in-time "
                    "serving feature row"
                ),
            )

        row = dict(rows[0])

        # Heat/Rain inference. The mart row is already the authoritative raw
        # feature contract; do not overwrite it from another operational mart.
        try:
            loaded_model = _get_ml_model()
            if loaded_model is None:
                raise ModelCompatibilityError("No compatible ML model could be loaded")

            all_predictions, all_standard_deviations = predict_with_ensemble_spread(
                loaded_model.estimator,
                row,
                horizon_days=horizon_days,
            )
            predictions = all_predictions[0]
            standard_deviations = all_standard_deviations[0]
            prediction_source = loaded_model.prediction_source
            model_version = loaded_model.model_version
            learned_components = _build_learned_components(
                predictions,
                standard_deviations,
            )
        except Exception:
            if _is_deployed_environment():
                log.error(
                    "ML forecast failed in %s for city '%s'.",
                    _environment_name(),
                    city_id,
                    exc_info=True,
                )
                raise HTTPException(
                    status_code=503,
                    detail="ML forecast model is temporarily unavailable",
                )

            log.warning(
                "ML forecast failed for city '%s'; using the explicit "
                "local-development Heat/Rain rule fallback.",
                city_id,
                exc_info=True,
            )
            if not _allow_development_fallback():
                raise HTTPException(
                    status_code=503,
                    detail="ML forecast model is temporarily unavailable",
                )
            fallback_predictions = _development_heat_rain_estimates(
                row,
                horizon_days,
            )
            prediction_source = "development_fallback_rule"
            model_version = None
            learned_components = _build_development_components(
                fallback_predictions
            )

        components = {
            **learned_components,
            **_build_rule_components(row, horizon_days),
        }
        # Keep the stable API key order while excluding unavailable components
        # only from total/driver selection.
        components = {name: components[name] for name in SUB_SCORE_NAMES}
        (
            best_driver,
            best_driver_method,
            total_estimated,
            total_margin,
            total_ci_lower,
            total_ci_upper,
            total_uncertainty_method,
        ) = _summarize_components(components)

        # ── Build weather trajectory for the selected horizon ──
        weather_trajectory = {}
        for d in range(1, horizon_days + 1):
            weather_trajectory[f"temp_max_plus_{d}d"] = _finite_float(
                row.get(f"temp_forecast_plus_{d}d")
            )
        # Include precip and wind for the target day
        weather_trajectory[f"precip_plus_{horizon_days}d"] = _finite_float(
            row.get(f"precip_forecast_plus_{horizon_days}d")
        )
        weather_trajectory[f"wind_plus_{horizon_days}d"] = _finite_float(
            row.get(f"wind_forecast_plus_{horizon_days}d")
        )

        return {
            "city_id": city_id,
            "horizon_days": horizon_days,
            "prediction_date": str(row["forecast_origin_date"]),
            "current_tipping_score": round(float(row["current_tipping_score"]), 1),
            "estimated_total_tipping_score": total_estimated,
            "total_confidence_margin": total_margin,
            "total_ci_lower": total_ci_lower,
            "total_ci_upper": total_ci_upper,
            "total_uncertainty_method": total_uncertainty_method,
            "forecast_primary_driver": best_driver,
            "forecast_primary_driver_method": best_driver_method,
            "sub_scores_forecast": components,
            "weather_trajectory": weather_trajectory,
            "prediction_source": prediction_source,
            "model_version": model_version,
            "forecast_method": "hybrid_ml_and_forecast_rules",
            "model_target_components": list(TARGET_SCORE_NAMES),
            "rule_based_components": list(RULE_BASED_SCORE_NAMES),
            "feature_schema_version": FEATURE_SCHEMA_VERSION,
            "feature_ingestion_run_id": str(row["ingestion_run_id"]),
            "feature_ingested_at_utc": str(row["ingested_at_utc"]),
            "forecast_origin_time_zone": str(row["forecast_origin_time_zone"]),
        }

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Error querying forecast for '{city_id}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve forecast data: {e}")
