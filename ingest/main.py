"""
main.py — ClimaSentinel ingest job entrypoint
Reads cities from config/cities.csv, fetches Open-Meteo data, loads into BigQuery raw tables.
Designed to run as a Cloud Run Job triggered by Cloud Scheduler (hourly).
"""

import csv
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from google.cloud import bigquery

from fetcher import fetch_weather_forecast, fetch_air_quality
from loader import insert_weather_rows, insert_air_quality_rows

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
log = logging.getLogger(__name__)

# ─── Configuration ────────────────────────────────────────────────────────────
# Load .env if running locally; on Cloud Run, env vars are injected directly
load_dotenv(Path(__file__).parent.parent / ".env")

PROJECT_ID   = os.environ["GCP_PROJECT_ID"]
DATASET_RAW  = os.getenv("BQ_DATASET_RAW", "raw")
CITIES_CSV   = Path(__file__).parent.parent / "config" / "cities.csv"


def load_cities() -> list[dict]:
    with open(CITIES_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [
            row for row in reader
            if row["active"].lower() == "true"
        ]


def run():
    run_id     = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc).isoformat()
    client     = bigquery.Client(project=PROJECT_ID)
    cities     = load_cities()

    log.info(f"Run {run_id} started — {len(cities)} active cities")

    total_weather_rows = 0
    total_air_rows     = 0
    errors             = []

    for city in cities:
        city_id = city["city_id"]
        log.info(f"  Processing {city_id}...")

        # ── Weather forecast ─────────────────────────────────────────────────
        try:
            weather_rows = fetch_weather_forecast(city)
            n = insert_weather_rows(
                client, PROJECT_ID, DATASET_RAW,
                weather_rows, run_id, started_at,
            )
            total_weather_rows += n
            log.info(f"    ✓ weather: {n} rows inserted")
        except Exception as e:
            msg = f"weather fetch/load failed for {city_id}: {e}"
            log.error(f"    ✗ {msg}")
            errors.append(msg)

        # ── Air quality ───────────────────────────────────────────────────────
        try:
            air_rows = fetch_air_quality(city)
            n = insert_air_quality_rows(
                client, PROJECT_ID, DATASET_RAW,
                air_rows, run_id, started_at,
            )
            total_air_rows += n
            log.info(f"    ✓ air quality: {n} rows inserted")
        except Exception as e:
            msg = f"air quality fetch/load failed for {city_id}: {e}"
            log.error(f"    ✗ {msg}")
            errors.append(msg)

    # ── Log run result ────────────────────────────────────────────────────────
    total_rows    = total_weather_rows + total_air_rows
    status        = "success" if not errors else "partial_failure" if total_rows > 0 else "failure"

    log.info(
        f"Run {run_id} complete — status={status} "
        f"weather={total_weather_rows} rows, air={total_air_rows} rows"
    )

    if status == "failure":
        raise SystemExit(1)


if __name__ == "__main__":
    run()
