"""
ClimaSentinel — FastAPI Backend

Endpoints:
  GET  /        → welcome message
  GET  /health  → health check
"""

import time
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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


# ── BigQuery Example ─────────────────────────────────────────────────────
from .db import get_bq_client
from fastapi import HTTPException
from google.cloud import bigquery

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
            SELECT city_id, current_tipping_score
            FROM `{settings.GCP_PROJECT_ID}.dbt_marts.mart_city_score_current`
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
