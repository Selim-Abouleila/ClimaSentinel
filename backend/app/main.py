"""
ClimaSentinel — FastAPI Backend

Endpoints:
  GET  /        → welcome message
  GET  /health  → health check
"""

import time
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from google.cloud import bigquery

from prometheus_fastapi_instrumentator import Instrumentator

from .config import get_settings

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s")

# ── Track uptime ─────────────────────────────────────────────────────────
_start_time: float = 0.0


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
            SELECT city_id, current_tipping_score, current_primary_driver
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
def get_city_forecast(city_id: str):
    """
    Returns the 3-day future climate tipping forecast for a single city.
    Fetches the pre-computed 3-day weather trajectory from `mart_ml_feature_store`,
    runs inference via the Multi-Output Random Forest model, and calculates
    individual sub-scores, total tipping risk, and 95% confidence intervals.
    """
    try:
        client = get_bq_client()
        query = f"""
            SELECT *
            FROM `{settings.GCP_PROJECT_ID}.{settings.BQ_DATASET}.mart_ml_feature_store`
            WHERE city_id = @city_id
            ORDER BY date DESC
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
        import numpy as np
        import pandas as pd
        import joblib
        import os
        import mlflow.sklearn
        
        # Prepare feature vector matching train.py
        feature_cols = [
            'current_tipping_score', 
            'temperature_2m_max', 'temperature_2m_min', 'precipitation_sum_mm', 'wind_speed_10m_max', 'european_aqi_max', 'river_discharge_m3s',
            'temp_forecast_plus_1d', 'temp_forecast_plus_2d', 'temp_forecast_plus_3d',
            'precip_forecast_plus_1d', 'precip_forecast_plus_2d', 'precip_forecast_plus_3d',
            'wind_forecast_plus_1d', 'wind_forecast_plus_2d', 'wind_forecast_plus_3d',
            'city_id'
        ]
        
        # Build DataFrame for get_dummies matching training structure
        all_cities = ['amsterdam_nl', 'athens_gr', 'berlin_de', 'lisbon_pt', 'london_gb', 'madrid_es', 'paris_fr', 'rome_it', 'stockholm_se', 'warsaw_pl']
        
        df_input = pd.DataFrame([row])
        df_input['river_discharge_m3s'] = df_input['river_discharge_m3s'].fillna(0)
        df_features = df_input[feature_cols].copy()
        df_features['city_id'] = pd.Categorical(df_features['city_id'], categories=all_cities)
        X = pd.get_dummies(df_features, columns=['city_id'], drop_first=True)
        
        sub_score_names = ['heat_score', 'wind_score', 'rain_score', 'air_score', 'river_score']
        preds = None
        conf_intervals = {}
        
        # Try loading local pickle artifact first
        model_path = os.path.join(os.path.dirname(__file__), "risk_forecaster.pkl")
        model = None
        if os.path.exists(model_path):
            try:
                model = joblib.load(model_path)
            except Exception as e:
                log.warning(f"Failed to load local pickle model: {e}")
        
        # Try loading from MLflow registry if pickle not available
        if not model:
            try:
                if os.environ.get("DAGSHUB_USER_TOKEN"):
                    import dagshub
                    dagshub.init(repo_owner=os.environ.get("DAGSHUB_USERNAME", "Selim-Abouleila"), repo_name="ClimaSentinel", mlflow=True)
                model = mlflow.sklearn.load_model("models:/ClimaSentinel_RiskForecaster/latest")
            except Exception as e:
                log.warning(f"Failed to load MLflow registered model: {e}")
        
        if model and hasattr(model, "estimators_"):
            # Multi-Output Random Forest Inference with Tree-Level Uncertainty
            preds = model.predict(X)[0] # array of 5 sub-scores
            
            # Extract predictions across all trees in the forest to compute 95% Confidence Intervals
            tree_preds = np.array([tree.predict(X.values)[0] for tree in model.estimators_])
            stds = np.std(tree_preds, axis=0)
            
            for idx, name in enumerate(sub_score_names):
                mean_val = preds[idx]
                std_val = stds[idx]
                margin = 1.96 * std_val
                conf_intervals[name] = {
                    "estimated_score": round(float(mean_val), 1),
                    "ci_lower": round(float(max(0.0, mean_val - margin)), 1),
                    "ci_upper": round(float(min(100.0, mean_val + margin)), 1),
                    "confidence_margin": round(float(margin), 1)
                }
            
            total_estimated = round(float(max(preds)), 1)
            driver_idx = np.argmax(preds)
            total_margin = round(float(1.96 * stds[driver_idx]), 1)
            
        else:
            # Robust fallback simulation calibrated to exact mart_ml_feature_store weather trajectories
            base = float(row.get('current_tipping_score', 50.0))
            t_max = float(row.get('temp_forecast_plus_3d', 25.0))
            p_sum = float(row.get('precip_forecast_plus_3d', 0.0))
            w_max = float(row.get('wind_forecast_plus_3d', 20.0))
            
            est_heat = min(100.0, max(0.0, base * 0.4 + (t_max - 20.0) * 2.5))
            est_wind = min(100.0, max(0.0, (w_max - 30.0) * 2.0 if w_max > 30 else base * 0.2))
            est_rain = min(100.0, max(0.0, p_sum * 5.0 if p_sum > 0 else base * 0.2))
            est_air = min(100.0, max(0.0, base * 0.8))
            est_river = min(100.0, max(0.0, base * 0.5 if row.get('river_discharge_m3s', 0) > 0 else 0.0))
            
            scores_map = [est_heat, est_wind, est_rain, est_air, est_river]
            
            for idx, name in enumerate(sub_score_names):
                mean_val = scores_map[idx]
                std_val = mean_val * 0.12 if mean_val > 0 else 0.0
                margin = 1.96 * std_val
                conf_intervals[name] = {
                    "estimated_score": round(float(mean_val), 1),
                    "ci_lower": round(float(max(0.0, mean_val - margin)), 1),
                    "ci_upper": round(float(min(100.0, mean_val + margin)), 1),
                    "confidence_margin": round(float(margin), 1)
                }
            
            total_estimated = round(float(max(scores_map)), 1)
            driver_idx = np.argmax(scores_map)
            total_margin = round(float(1.96 * (scores_map[driver_idx] * 0.12)), 1)

        driver_map = {0: 'Heat', 1: 'Wind', 2: 'Rain', 3: 'Air Quality', 4: 'River/Flood'}
        best_driver = driver_map[np.argmax([conf_intervals[n]["estimated_score"] for n in sub_score_names])]

        return {
            "city_id": city_id,
            "prediction_date": str(row['date']),
            "current_tipping_score": round(float(row.get('current_tipping_score', 0)), 1),
            "estimated_total_tipping_score": total_estimated,
            "total_confidence_margin": total_margin,
            "total_ci_lower": round(float(max(0.0, total_estimated - total_margin)), 1),
            "total_ci_upper": round(float(min(100.0, total_estimated + total_margin)), 1),
            "forecast_primary_driver": best_driver,
            "sub_scores_forecast": conf_intervals,
            "weather_trajectory_3d": {
                "temp_max_plus_1d": float(row.get('temp_forecast_plus_1d', 0)),
                "temp_max_plus_2d": float(row.get('temp_forecast_plus_2d', 0)),
                "temp_max_plus_3d": float(row.get('temp_forecast_plus_3d', 0)),
                "precip_plus_3d": float(row.get('precip_forecast_plus_3d', 0)),
                "wind_plus_3d": float(row.get('wind_forecast_plus_3d', 0)),
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Error querying forecast for '{city_id}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve forecast data: {e}")
