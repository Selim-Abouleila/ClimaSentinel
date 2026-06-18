"""
ClimaSentinel — FastAPI Backend

Endpoints:
  GET  /              → welcome message
  GET  /health        → health check (model status, uptime)
  POST /predict       → run prediction for a city
  GET  /cities        → list valid cities
  GET  /metrics       → Prometheus metrics
"""

import time
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .schemas import (
    PredictionRequest,
    PredictionResponse,
    HealthResponse,
    ErrorResponse,
)
from .model_service import load_model, is_model_loaded, get_model_version, predict, VALID_CITIES
from .metrics import (
    REQUEST_COUNT,
    REQUEST_LATENCY,
    ERROR_COUNT,
    APP_INFO,
    get_metrics,
)

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
    APP_INFO.info({
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
    })

    log.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION} [{settings.ENVIRONMENT}]")
    load_model()
    yield
    log.info("Shutting down.")


# ── App ──────────────────────────────────────────────────────────────────
settings = get_settings()

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Climate prediction API for 10 European cities",
    lifespan=lifespan,
)

# CORS — allow the frontend (React/Next.js) to call this API
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


@app.get("/health", response_model=HealthResponse, tags=["General"])
def health():
    return HealthResponse(
        status="healthy",
        environment=settings.ENVIRONMENT,
        model_loaded=is_model_loaded(),
        model_version=get_model_version(),
        uptime_seconds=round(time.time() - _start_time, 2),
    )


@app.get("/cities", tags=["General"])
def list_cities():
    return {"cities": VALID_CITIES}


@app.post(
    "/predict",
    response_model=PredictionResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    tags=["Predictions"],
)
def make_prediction(req: PredictionRequest):
    start = time.time()
    city = req.city.strip().title()

    try:
        result = predict(city, req.date)
        elapsed = time.time() - start

        REQUEST_COUNT.labels(city=city, status="success").inc()
        REQUEST_LATENCY.labels(city=city).observe(elapsed)

        log.info(f"Prediction for {city} — {elapsed:.3f}s")
        return result

    except ValueError as exc:
        REQUEST_COUNT.labels(city=city, status="error").inc()
        ERROR_COUNT.labels(city=city, error_type="validation").inc()
        raise HTTPException(status_code=400, detail=str(exc))

    except Exception as exc:
        REQUEST_COUNT.labels(city=city, status="error").inc()
        ERROR_COUNT.labels(city=city, error_type="internal").inc()
        log.exception(f"Prediction failed for {city}")
        raise HTTPException(status_code=500, detail="Internal prediction error")


@app.get("/metrics", tags=["Monitoring"], include_in_schema=False)
def metrics():
    """Prometheus-compatible metrics endpoint."""
    body, content_type = get_metrics()
    return Response(content=body, media_type=content_type)
