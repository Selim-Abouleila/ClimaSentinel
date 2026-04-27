"""
main.py — ClimaSentinel ingest job entrypoint
Reads cities from config/cities.csv, fetches Open-Meteo data, loads into BigQuery raw tables.
Designed to run as a Cloud Run Job triggered by Cloud Scheduler (daily at 06:00 UTC).

Sources fetched per run:
  All cities:
    - Weather Forecast  → raw.weather_forecast_hourly   (168 rows/city, hourly, 7 days)
    - Air Quality       → raw.air_quality_hourly         (120 rows/city, hourly, 5 days)
    - Historical (ERA5) → raw.historical_weather_daily   (7 rows/city, daily, rolling)
  River-enabled cities only:
    - Flood/River       → raw.flood_daily                (7 rows/city, daily, 7 days)
  All cities, 1st of month only:
    - Climate (CMIP6)   → raw.climate_projections_daily  (~3650 rows/city, 10-year window)
"""

import csv
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from google.cloud import bigquery

from fetcher import (
    fetch_air_quality,
    fetch_climate_projection,
    fetch_flood_discharge,
    fetch_historical_weather,
    fetch_weather_forecast,
)
from loader import (
    insert_air_quality_rows,
    insert_climate_projection_rows,
    insert_flood_rows,
    insert_historical_weather_rows,
    insert_weather_rows,
)

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
log = logging.getLogger(__name__)

# ─── Configuration ────────────────────────────────────────────────────────────
load_dotenv(Path(__file__).parent.parent / ".env")

PROJECT_ID  = os.environ["GCP_PROJECT_ID"]
DATASET_RAW = os.getenv("BQ_DATASET_RAW", "raw")
CITIES_CSV  = Path(__file__).parent.parent / "config" / "cities.csv"


def load_cities() -> list[dict]:
    with open(CITIES_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [row for row in reader if row["active"].lower() == "true"]


def _fetch_and_insert(label: str, fetch_fn, insert_fn, city, client, run_id, started_at, errors) -> int:
    """Generic try/except wrapper for a single fetch+insert pair."""
    try:
        rows = fetch_fn(city)
        if not rows:
            log.info(f"    ~ {label}: skipped (no data / guard active)")
            return 0
        n = insert_fn(client, PROJECT_ID, DATASET_RAW, rows, run_id, started_at)
        log.info(f"    + {label}: {n} rows inserted")
        return n
    except Exception as e:
        msg = f"{label} failed for {city['city_id']}: {e}"
        log.error(f"    x {msg}")
        errors.append(msg)
        return 0


def run():
    run_id     = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc).isoformat()
    client     = bigquery.Client(project=PROJECT_ID)
    cities     = load_cities()

    log.info(f"Run {run_id} started — {len(cities)} active cities")

    totals = {
        "weather":     0,
        "air_quality": 0,
        "flood":       0,
        "historical":  0,
        "climate":     0,
    }
    errors = []

    for city in cities:
        log.info(f"  Processing {city['city_id']}...")

        totals["weather"]    += _fetch_and_insert("weather",    fetch_weather_forecast,   insert_weather_rows,            city, client, run_id, started_at, errors)
        totals["air_quality"]+= _fetch_and_insert("air_quality",fetch_air_quality,        insert_air_quality_rows,        city, client, run_id, started_at, errors)
        totals["historical"] += _fetch_and_insert("historical", fetch_historical_weather, insert_historical_weather_rows, city, client, run_id, started_at, errors)
        totals["climate"]    += _fetch_and_insert("climate",    fetch_climate_projection, insert_climate_projection_rows, city, client, run_id, started_at, errors)

        # Flood only for river-enabled cities
        if city.get("river_enabled", "false").lower() == "true":
            totals["flood"] += _fetch_and_insert("flood", fetch_flood_discharge, insert_flood_rows, city, client, run_id, started_at, errors)

    # ── Summary ───────────────────────────────────────────────────────────────
    total_rows = sum(totals.values())
    status     = "success" if not errors else "partial_failure" if total_rows > 0 else "failure"

    log.info(
        f"Run {run_id} complete — status={status} | "
        + " | ".join(f"{k}={v}" for k, v in totals.items())
    )

    if errors:
        for err in errors:
            log.warning(f"  Error logged: {err}")

    if status == "failure":
        raise SystemExit(1)


if __name__ == "__main__":
    run()
