"""
loader.py — BigQuery insert logic
Handles streaming inserts into raw.* and ops.ingestion_runs.
"""

from datetime import datetime, timezone
from google.cloud import bigquery

# BigQuery table schemas (used for create-if-not-exists)
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

OPS_SCHEMA = [
    bigquery.SchemaField("ingestion_run_id", "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("source_name",      "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("started_at_utc",   "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("finished_at_utc",  "TIMESTAMP", mode="NULLABLE"),
    bigquery.SchemaField("status",           "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("rows_loaded",      "INT64",     mode="NULLABLE"),
    bigquery.SchemaField("error_message",    "STRING",    mode="NULLABLE"),
]


def _ensure_table(client: bigquery.Client, table_ref: str, schema: list, partition_field: str | None = None):
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
        row["ingested_at_utc"] = ingested_at
    return rows


def insert_weather_rows(
    client: bigquery.Client,
    project: str,
    dataset: str,
    rows: list[dict],
    run_id: str,
    ingested_at: str,
) -> int:
    table_ref = f"{project}.{dataset}.weather_forecast_hourly"
    _ensure_table(client, table_ref, WEATHER_SCHEMA, partition_field="valid_ts_utc")
    stamped = _stamp_rows(rows, run_id, ingested_at)
    errors = client.insert_rows_json(table_ref, stamped)
    if errors:
        raise RuntimeError(f"BQ insert errors (weather): {errors}")
    return len(stamped)


def insert_air_quality_rows(
    client: bigquery.Client,
    project: str,
    dataset: str,
    rows: list[dict],
    run_id: str,
    ingested_at: str,
) -> int:
    table_ref = f"{project}.{dataset}.air_quality_hourly"
    _ensure_table(client, table_ref, AIR_QUALITY_SCHEMA, partition_field="valid_ts_utc")
    stamped = _stamp_rows(rows, run_id, ingested_at)
    errors = client.insert_rows_json(table_ref, stamped)
    if errors:
        raise RuntimeError(f"BQ insert errors (air_quality): {errors}")
    return len(stamped)


def log_run(
    client: bigquery.Client,
    project: str,
    dataset: str,
    run_id: str,
    source_name: str,
    started_at: str,
    status: str,
    rows_loaded: int = 0,
    error_message: str | None = None,
):
    table_ref = f"{project}.{dataset}.ingestion_runs"
    _ensure_table(client, table_ref, OPS_SCHEMA, partition_field="started_at_utc")

    row = {
        "ingestion_run_id": run_id,
        "source_name":      source_name,
        "started_at_utc":   started_at,
        "finished_at_utc":  datetime.now(timezone.utc).isoformat(),
        "status":           status,
        "rows_loaded":      rows_loaded,
        "error_message":    error_message,
    }
    errors = client.insert_rows_json(table_ref, [row])
    if errors:
        raise RuntimeError(f"BQ insert errors (ops): {errors}")
