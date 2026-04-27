"""
loader.py — BigQuery insert logic
Handles streaming inserts into raw.* tables.
"""

from datetime import datetime, timezone
from google.cloud import bigquery

# ─── BigQuery table schemas (used for create-if-not-exists) ───────────────────

WEATHER_SCHEMA = [
    bigquery.SchemaField("ingestion_run_id",  "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("ingested_at_utc",   "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("city_id",           "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("valid_ts_utc",      "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("temperature_2m",    "FLOAT64",   mode="NULLABLE"),
    bigquery.SchemaField("precipitation_mm",  "FLOAT64",   mode="NULLABLE"),
    bigquery.SchemaField("wind_speed_10m",    "FLOAT64",   mode="NULLABLE"),
    bigquery.SchemaField("wind_gusts_10m",    "FLOAT64",   mode="NULLABLE"),
    bigquery.SchemaField("weather_code",      "INT64",     mode="NULLABLE"),
]

AIR_QUALITY_SCHEMA = [
    bigquery.SchemaField("ingestion_run_id", "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("ingested_at_utc",  "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("city_id",          "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("valid_ts_utc",     "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("european_aqi",     "FLOAT64",   mode="NULLABLE"),
    bigquery.SchemaField("pm2_5",            "FLOAT64",   mode="NULLABLE"),
    bigquery.SchemaField("pm10",             "FLOAT64",   mode="NULLABLE"),
    bigquery.SchemaField("no2",              "FLOAT64",   mode="NULLABLE"),
    bigquery.SchemaField("o3",               "FLOAT64",   mode="NULLABLE"),
]

FLOOD_SCHEMA = [
    bigquery.SchemaField("ingestion_run_id",    "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("ingested_at_utc",     "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("city_id",             "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("date",                "DATE",      mode="REQUIRED"),
    bigquery.SchemaField("river_discharge_m3s", "FLOAT64",   mode="NULLABLE"),
]

HISTORICAL_WEATHER_SCHEMA = [
    bigquery.SchemaField("ingestion_run_id",    "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("ingested_at_utc",     "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("city_id",             "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("date",                "DATE",      mode="REQUIRED"),
    bigquery.SchemaField("temperature_2m_mean", "FLOAT64",   mode="NULLABLE"),
    bigquery.SchemaField("temperature_2m_max",  "FLOAT64",   mode="NULLABLE"),
    bigquery.SchemaField("temperature_2m_min",  "FLOAT64",   mode="NULLABLE"),
    bigquery.SchemaField("precipitation_sum_mm","FLOAT64",   mode="NULLABLE"),
    bigquery.SchemaField("wind_speed_10m_max",  "FLOAT64",   mode="NULLABLE"),
]

CLIMATE_PROJECTION_SCHEMA = [
    bigquery.SchemaField("ingestion_run_id",    "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("ingested_at_utc",     "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("city_id",             "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("date",                "DATE",      mode="REQUIRED"),
    bigquery.SchemaField("model",               "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("temperature_2m_max",  "FLOAT64",   mode="NULLABLE"),
    bigquery.SchemaField("temperature_2m_min",  "FLOAT64",   mode="NULLABLE"),
    bigquery.SchemaField("precipitation_sum_mm","FLOAT64",   mode="NULLABLE"),
    bigquery.SchemaField("wind_speed_10m_max",  "FLOAT64",   mode="NULLABLE"),
]

# ──────────────────────────────────────────────────────────────────────────────


def _ensure_table(
    client: bigquery.Client,
    table_ref: str,
    schema: list,
    partition_field: str | None = None,
):
    """Create table if it does not already exist."""
    table = bigquery.Table(table_ref, schema=schema)
    if partition_field:
        table.time_partitioning = bigquery.TimePartitioning(
            type_=bigquery.TimePartitioningType.DAY,
            field=partition_field,
        )
    client.create_table(table, exists_ok=True)


def _stamp_rows(rows: list[dict], run_id: str, ingested_at: str) -> list[dict]:
    """Inject ingestion metadata into every row."""
    for row in rows:
        row["ingestion_run_id"] = run_id
        row["ingested_at_utc"]  = ingested_at
    return rows


def _insert(
    client: bigquery.Client,
    table_ref: str,
    schema: list,
    rows: list[dict],
    run_id: str,
    ingested_at: str,
    partition_field: str,
    label: str,
) -> int:
    """Generic ensure + stamp + insert helper."""
    _ensure_table(client, table_ref, schema, partition_field=partition_field)
    stamped = _stamp_rows(rows, run_id, ingested_at)
    errors  = client.insert_rows_json(table_ref, stamped)
    if errors:
        raise RuntimeError(f"BQ insert errors ({label}): {errors}")
    return len(stamped)


# ─── Public insert functions ──────────────────────────────────────────────────

def insert_weather_rows(client, project, dataset, rows, run_id, ingested_at) -> int:
    return _insert(
        client, f"{project}.{dataset}.weather_forecast_hourly",
        WEATHER_SCHEMA, rows, run_id, ingested_at,
        partition_field="valid_ts_utc", label="weather",
    )


def insert_air_quality_rows(client, project, dataset, rows, run_id, ingested_at) -> int:
    return _insert(
        client, f"{project}.{dataset}.air_quality_hourly",
        AIR_QUALITY_SCHEMA, rows, run_id, ingested_at,
        partition_field="valid_ts_utc", label="air_quality",
    )


def insert_flood_rows(client, project, dataset, rows, run_id, ingested_at) -> int:
    return _insert(
        client, f"{project}.{dataset}.flood_daily",
        FLOOD_SCHEMA, rows, run_id, ingested_at,
        partition_field="date", label="flood",
    )


def insert_historical_weather_rows(client, project, dataset, rows, run_id, ingested_at) -> int:
    return _insert(
        client, f"{project}.{dataset}.historical_weather_daily",
        HISTORICAL_WEATHER_SCHEMA, rows, run_id, ingested_at,
        partition_field="date", label="historical_weather",
    )


def insert_climate_projection_rows(client, project, dataset, rows, run_id, ingested_at) -> int:
    return _insert(
        client, f"{project}.{dataset}.climate_projections_daily",
        CLIMATE_PROJECTION_SCHEMA, rows, run_id, ingested_at,
        partition_field="date", label="climate_projection",
    )
