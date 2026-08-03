"""
ClimaSentinel — FastAPI Backend

Endpoints:
  GET  /        → welcome message
  GET  /health  → health check
"""

import logging
import math
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from google.cloud import bigquery

from prometheus_fastapi_instrumentator import Instrumentator

from .config import get_settings
from .forecast_rules import forecast_rule_estimates
from .ml_pipeline import (
    FEATURE_SCHEMA_VERSION,
    ModelCompatibilityError,
)
from .schemas import (
    CityForecastResponse,
    CityScoreDetailResponse,
    CityScoreHistoryResponse,
    CurrentCityScoreResponse,
)

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s")

# ── Track uptime ─────────────────────────────────────────────────────────
_start_time: float = 0.0

SUB_SCORE_NAMES = (
    "heat_score",
    "wind_score",
    "rain_score",
    "air_score",
    "river_score",
)
RULE_BASED_SCORE_NAMES = tuple(
    name.removesuffix("_score") for name in SUB_SCORE_NAMES
)
DRIVER_LABELS = {
    "heat_score": "Heat",
    "wind_score": "Wind",
    "rain_score": "Rain",
    "air_score": "Air Quality",
    "river_score": "River/Flood",
}
CURRENT_SCORES_DEFAULT_LIMIT = 100
CURRENT_SCORES_MAX_LIMIT = 100


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
            "validation_status": estimate.validation_status,
            "uncertainty_method": "none",
            "provenance": estimate.provenance,
            "method_reason": estimate.method_reason,
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

@app.get(
    "/data/current-scores",
    tags=["Data"],
    response_model=list[CurrentCityScoreResponse],
)
def get_current_scores(
    limit: int = Query(
        default=CURRENT_SCORES_DEFAULT_LIMIT,
        ge=1,
        le=CURRENT_SCORES_MAX_LIMIT,
        description="Maximum number of current city scores to return",
    ),
):
    """
    Return the current city ranking from `mart_city_score_current_v2`.

    The bounded default is intentionally larger than the operational city
    registry so dashboard growth is not silently truncated.
    """
    try:
        client = get_bq_client()
        # Querying the current scores mart as an example
        query = f"""
            SELECT
                operational_ingestion_run_id,
                operational_ingested_at_utc,
                city_id,
                current_tipping_score,
                current_primary_driver,
                current_score_available,
                monitored_factor_count,
                available_factor_count,
                overall_coverage,
                rank
            FROM `{settings.GCP_PROJECT_ID}.{settings.BQ_DATASET}.mart_city_score_current_v2`
            ORDER BY current_score_available DESC, rank ASC, city_id ASC
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


@app.get(
    "/data/history-scores",
    tags=["Data"],
    response_model=list[CityScoreHistoryResponse],
)
def get_history_scores(city_id: str = None, limit: int = 50):
    """
    Returns historical tipping scores from `mart_city_score_history_v2`.
    """
    try:
        client = get_bq_client()
        query = f"SELECT * FROM `{settings.GCP_PROJECT_ID}.{settings.BQ_DATASET}.mart_city_score_history_v2`"
        query_parameters = [bigquery.ScalarQueryParameter("limit", "INT64", limit)]
        if city_id:
            query += " WHERE city_id = @city_id"
            query_parameters.append(bigquery.ScalarQueryParameter("city_id", "STRING", city_id))
        query += " ORDER BY date DESC LIMIT @limit"
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
    Returns current tipping zones from `mart_city_zone_current_v2`.
    """
    try:
        client = get_bq_client()
        query = f"SELECT * FROM `{settings.GCP_PROJECT_ID}.{settings.BQ_DATASET}.mart_city_zone_current_v2` LIMIT @limit"
        job_config = bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter("limit", "INT64", limit)])
        query_job = client.query(query, job_config=job_config)
        results = query_job.result()
        return [dict(row) for row in results]
    except Exception as e:
        log.error(f"Error querying BigQuery zones: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve zones data")


@app.get(
    "/data/city/{city_id}/scores",
    tags=["Data"],
    response_model=CityScoreDetailResponse,
)
def get_city_scores(city_id: str):
    """
    Returns the individual tipping sub-scores (heat, wind, rain, air, river)
    for a single city across today and tomorrow in UTC. Each score carries
    explicit monitoring, availability, status and input-coverage metadata.
    Unavailable and unmonitored scores remain null instead of becoming 0.

    Source table : mart_city_score_detail_v2 (a view over
                   mart_city_score_history_v2).

    Returns 404 if the city_id is not found in the mart.
    """
    try:
        client = get_bq_client()
        query = f"""
            SELECT
                operational_ingestion_run_id,
                operational_ingested_at_utc,
                city_id,
                score_date,
                current_tipping_score,
                current_primary_driver,
                current_score_available,
                monitored_factor_count,
                available_factor_count,
                overall_coverage,
                heat_score,
                heat_status,
                heat_monitored,
                heat_available,
                heat_coverage,
                wind_score,
                wind_status,
                wind_monitored,
                wind_available,
                wind_coverage,
                rain_score,
                rain_status,
                rain_monitored,
                rain_available,
                rain_coverage,
                air_score,
                air_status,
                air_monitored,
                air_available,
                air_coverage,
                river_score,
                river_status,
                river_monitored,
                river_available,
                river_coverage
            FROM `{settings.GCP_PROJECT_ID}.{settings.BQ_DATASET}.mart_city_score_detail_v2`
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
                detail=f"City '{city_id}' not found in mart_city_score_detail_v2"
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
    Return the rule-baseline Day +1, +2 or +3 forecast for one city.

    Every component is calculated from the same exact forecast vintage. Heat
    uses the target month's city climatology and has limited backtest evidence
    against Open-Meteo archive/reanalysis data. Rain was backtested against the
    same source but showed insufficient predictive skill. Wind, Air Quality and
    River/Flood still lack observed-label validation. Missing optional sources
    remain unavailable rather than being reported as zero, and deterministic
    rules never expose model confidence intervals.
    """
    try:
        client = get_bq_client()
        query = f"""
            SELECT
                serving.*,
                target_normals.normal_temperature_2m_max
                    AS target_normal_temperature_2m_max
            FROM `{settings.GCP_PROJECT_ID}.{settings.BQ_DATASET}.mart_ml_serving_features_current`
                AS serving
            LEFT JOIN `{settings.GCP_PROJECT_ID}.{settings.BQ_STAGING_DATASET}.city_monthly_normals`
                AS target_normals
                ON serving.city_id = target_normals.city_id
                AND EXTRACT(
                    MONTH FROM DATE_ADD(
                        serving.forecast_origin_date,
                        INTERVAL @horizon_days DAY
                    )
                ) = target_normals.month
            WHERE serving.city_id = @city_id
              AND serving.forecast_age_days = 0
              AND serving.is_canonical_daily_vintage
              AND serving.has_expected_horizon_dates
              AND serving.has_complete_weather_feature_window
            ORDER BY serving.ingested_at_utc DESC, serving.ingestion_run_id DESC
            LIMIT 1
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("city_id", "STRING", city_id),
                bigquery.ScalarQueryParameter(
                    "horizon_days",
                    "INT64",
                    horizon_days,
                ),
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

        # Serving the deterministic baseline is an explicit reviewed policy,
        # not an exception-time fallback or a request-time quality guess. A
        # registry promotion does not change this path automatically.
        components = _build_rule_components(row, horizon_days)
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
            "prediction_source": "same_vintage_forecast_rules",
            "model_version": None,
            "forecast_method": "forecast_rules_baseline",
            "model_target_components": [],
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
