# 2. Ingestion Pipeline

The ClimaSentinel ingestion pipeline is a serverless, automated data pipeline
running on Google Cloud Platform. It scales to zero when idle and actively
fetches weather forecasts, air-quality forecasts, river-discharge forecasts and
lagged historical reanalysis for a configurable set of cities. Support code for
long-term CMIP6 projections remains in the repository, but that fetch is
disabled in scheduled ingestion.

## Architecture

The ingestion process relies on three core Google Cloud services, all provisioned via Terraform:
1. **Cloud Scheduler**: Acts as a cron job, firing an HTTP request to the Cloud Run job once a day at `06:00 UTC` (`0 6 * * *`).
2. **Cloud Run Job**: Executes the Python runner which contains the application logic to pull from APIs and transform the results.
3. **BigQuery**: Provides the data warehouse where processed, raw climate data is appended into time-partitioned tables.

Additionally, **Artifact Registry** is used to store the Docker container image built via **Cloud Build**.

## Configuration: The City List

The ingestion script iterates over 10 major European cities configured in
`config/cities.csv`. To add or remove cities, update the CSV, then rebuild and
redeploy the ingestion image; pushing the file alone does not update the running
Cloud Run Job. The `river_enabled` column controls whether flood/river discharge
data is fetched for that city.

| City | Country | Latitude | Longitude | River Monitoring |
|---|---|---|---|---|
| Paris | FR | 48.853 | 2.348 | ✅ |
| London | GB | 51.508 | -0.125 | — |
| Madrid | ES | 40.416 | -3.702 | — |
| Berlin | DE | 52.524 | 13.410 | — |
| Rome | IT | 41.891 | 12.511 | — |
| Amsterdam | NL | 52.374 | 4.889 | ✅ |
| Athens | GR | 37.983 | 23.727 | — |
| Warsaw | PL | 52.229 | 21.011 | ✅ |
| Lisbon | PT | 38.716 | -9.133 | — |
| Stockholm | SE | 59.329 | 18.068 | — |

---

## APIs & Data Retrieved

The scheduled Cloud Run job actively calls four Open-Meteo endpoint families,
formats the responses as JSON, and streams them into the `raw` BigQuery dataset.
Flood is called only for river-enabled cities. A fifth CMIP6 client exists but
is not invoked by `ingest/main.py`. Because active tables are time-partitioned,
no data is overwritten; historical forecast vintages accumulate over time.

### 1. Weather Forecast (`raw.weather_forecast_hourly`)
- **Endpoint**: `api.open-meteo.com/v1/forecast`
- **Cadence**: Daily (all cities)
- **Time Window**: Next 7 Days (Hourly) = **168 rows per city per day**
- **Variables Retrieved**:
  - `temperature_2m` (°C at 2 meters)
  - `precipitation_mm` (mm/hour)
  - `wind_speed_10m` (km/h)
  - `wind_gusts_10m` (km/h)
  - `weather_code` (WMO Weather interpretation codes)

### 2. Air Quality (`raw.air_quality_hourly`)
- **Endpoint**: `air-quality-api.open-meteo.com/v1/air-quality`
- **Cadence**: Daily (all cities)
- **Time Window**: Next 5 Days (Hourly) = **120 rows per city per day**
- **Variables Retrieved**:
  - `european_aqi` (European Air Quality Index, 0–500 scale)
  - `pm2_5` (Particulate Matter < 2.5 µm in µg/m³)
  - `pm10` (Particulate Matter < 10 µm in µg/m³)
  - `nitrogen_dioxide` (NO₂ in µg/m³)
  - `o3` (Ozone in µg/m³)

### 3. River Discharge (`raw.flood_daily`)
- **Endpoint**: `flood-api.open-meteo.com/v1/flood`
- **Cadence**: Daily (river-enabled cities only — Paris, Amsterdam, Warsaw)
- **Time Window**: Next 7 Days (Daily) = **7 rows per city per day**
- **Variables Retrieved**:
  - `river_discharge_m3s` (River discharge in m³/s — nearest river within 5 km of coordinates)

### 4. Historical Weather — ERA5 Reanalysis (`raw.historical_weather_daily`)
- **Endpoint**: `archive-api.open-meteo.com/v1/archive`
- **Cadence**: Daily (all cities)
- **Time Window**: Rolling 7-day window (`today-12` to `today-6`) = **7 rows per city per day**
- **Note**: ERA5 has a publication lag. The fetch window is deliberately offset
  to reduce the chance of ingesting partial recent data; source completeness
  should still be checked rather than assumed.
- **Variables Retrieved**:
  - `temperature_2m_mean` (Daily mean temperature in °C)
  - `temperature_2m_max` (Daily maximum temperature in °C)
  - `temperature_2m_min` (Daily minimum temperature in °C)
  - `precipitation_sum_mm` (Total daily precipitation in mm)
  - `wind_speed_10m_max` (Maximum daily wind speed in km/h)

### 5. Climate Projections — CMIP6 (implemented, scheduled fetch disabled)

- **Scheduled status**: Disabled; `ingest/main.py` does not currently invoke the
  fetch or loader, so no monthly rows or table creation should be expected
- **Endpoint**: `climate-api.open-meteo.com/v1/climate`
- **Guard if invoked directly**: 1st of month only
- **Time Window**: Next 10 years (Daily) = **~3,650 rows per city per month**
- **Model**: `MRI_AGCM3_2_S` (high-resolution atmospheric model)
- **Variables Retrieved**:
  - `temperature_2m_max` (Projected daily maximum temperature in °C)
  - `temperature_2m_min` (Projected daily minimum temperature in °C)
  - `precipitation_sum_mm` (Projected total daily precipitation in mm)
  - `wind_speed_10m_max` (Projected maximum daily wind speed in km/h)

---

## Daily Volume Summary

| Source | Rows/city/run | Cities | Frequency | Daily Total |
|---|---|---|---|---|
| Weather Forecast | 168 | 10 | Daily | 1,680 |
| Air Quality | 120 | 10 | Daily | 1,200 |
| River Discharge | 7 | 3 | Daily | 21 |
| Historical (ERA5) | 7 | 10 | Daily | 70 |
| Climate (CMIP6) | ~3,650 | 10 | Disabled | 0 scheduled |
| **Daily total** | | | | **~2,971** |

---

## Ingestion Metadata

Every row inserted into BigQuery is stamped with two metadata fields for traceability:

| Field | Type | Description |
|---|---|---|
| `ingestion_run_id` | `STRING` | UUID v4 unique to each pipeline run |
| `ingested_at_utc` | `TIMESTAMP` | UTC timestamp when the run started |

These fields enable deduplication in the staging layer and full audit trail of when each row was loaded.

## Table Auto-Creation

The active Python loaders use `client.create_table(exists_ok=True)` to create
their four raw tables on first successful use. They do **not** create the `raw`
dataset itself; it must already exist in the configured BigQuery location, as
described in [Doc 1](1-bootstrap-initialization.md). The optional
`climate_projections_daily` table is not auto-created while the CMIP6 call
remains disabled.

---

## Post-Ingestion: Automated dbt Run

Unless the run records source errors and inserts zero rows, the Cloud Run Job
invokes `dbt seed` and then `dbt run` to rebuild the Silver staging views and
Gold mart relations in the same execution. Partial ingestion therefore still
starts the transform step; an unusual zero-row run with no recorded exception
does too.

### How it works

```
Cloud Scheduler (06:00 UTC)
    → Cloud Run Job starts
        → [1] Ingest: fetch 4 active source families → raw.* tables
        → [2] Transform: dbt seed + dbt run → stg.* + mart.*
    → Job exits
```

The `run_dbt()` function in `main.py` invokes dbt as subprocesses using the
`transform/` directory bundled inside the Docker image and the `prod` target:

```python
subprocess.run([
    "dbt", "--no-use-colors", "seed",
    "--project-dir", "/app/transform",
    "--profiles-dir", "/app/transform",
    "--target", "prod",
], check=True)

subprocess.run([
    "dbt", "--no-use-colors", "run",
    "--project-dir", "/app/transform",
    "--profiles-dir", "/app/transform",
    "--target", "prod",
], check=True)
```

Authentication is handled automatically via the Cloud Run Job's service account — no JSON key file is required (`method: oauth` in `profiles.yml`).

### Failure behaviour

| Scenario | Outcome |
|---|---|
| All active fetch/insert attempts fail (errors and 0 rows inserted) | Job exits with code 1 — dbt is **not** triggered |
| Ingestion partial success (some rows inserted) | dbt seed/run is attempted against the available data |
| `dbt seed` or `dbt run` fails | Logged as `ERROR`, but the process currently returns normally and the Cloud Run execution can still appear successful |
| dbt tests | **Not run** by the scheduled ingestion job; run `make dbt-test` or `dbt test` separately |

> **Operational warning:** a green Cloud Run execution does not prove that the
> Silver and Gold layers refreshed. Raw streaming inserts are already durable
> before dbt starts, so swallowing a dbt error is not required to preserve
> them. Until the runner propagates transform failures, monitor the dbt log
> markers explicitly and run tests in a separate validation step.

### Verifying in logs

In GCP Console → **Cloud Run** → **Jobs** → `clima-sentinel-ingest` → select an execution → **Logs**, you will see:

```
── dbt run starting ──────────────────────────────────────────────
Running with dbt=1.x.x
...
Completed successfully
── dbt run complete ✓ ──────────────────────────────────────────
```

If dbt fails, the log will show:
```
── dbt run FAILED (exit 1) — mart tables may be stale. Check logs above for details.
```
