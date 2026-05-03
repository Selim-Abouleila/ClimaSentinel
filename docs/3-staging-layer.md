# 3. Staging Layer (Silver)

The staging layer transforms raw, append-only ingested data into clean, deduplicated, and harmonized views in BigQuery. It uses **dbt** (data build tool) to manage SQL transformations with dependency ordering, schema tests, and auto-generated documentation.

## Purpose

The `raw.*` tables accumulate overlapping data on every ingestion run (e.g., 168 hourly weather rows per city per day, with 6 days of overlap between consecutive runs). Before computing tipping scores, we need to:

1. **Deduplicate** — Keep only the freshest forecast for each `(city_id, timestamp)` pair
2. **Handle nulls** — Coalesce missing sensor readings to avoid downstream errors
3. **Harmonize grain** — Roll hourly tables down to daily summaries so all signals share the same `(city_id, date)` key
4. **Unify** — JOIN all signals into a single `stg.city_signal_input` table for the mart layer

---

## Model Dependency Graph

```
raw.weather_forecast_hourly ──→ stg_latest_weather_hourly ──→ stg_city_daily_weather ──┐
raw.air_quality_hourly ────────→ stg_latest_air_quality_hourly → stg_city_daily_air_quality ─┤
raw.flood_daily ───────────────→ stg_latest_flood_daily ───────────────────────────────────────┤
raw.historical_weather_daily ──→ stg_latest_historical_daily ──────────────────────────────────┤
                                                                                                ▼
                                                                              stg_city_signal_input
                                                                                        │
                                                                                        ▼
                                                                              (mart layer — next)
```

---

## Models

### Static Seeds (1)

Static configuration data loaded directly into BigQuery tables via `dbt seed`.

| Seed | Description | Source |
|---|---|---|
| `city_monthly_normals` | 10-year historical averages (2014-2023) for temp, rain, wind per month. Used by Gold layer as the absolute baseline to compute tipping deviations. | `transform/seeds/city_monthly_normals.csv` (generated from Open-Meteo ERA5) |

### Deduplication Views (4)

These views apply a `ROW_NUMBER() OVER (PARTITION BY ... ORDER BY ingested_at_utc DESC)` pattern to keep only the most recently ingested row for each natural key.

| Model | Source | Dedup Key |
|---|---|---|
| `stg_latest_weather_hourly` | `raw.weather_forecast_hourly` | `(city_id, valid_ts_utc)` |
| `stg_latest_air_quality_hourly` | `raw.air_quality_hourly` | `(city_id, valid_ts_utc)` |
| `stg_latest_flood_daily` | `raw.flood_daily` | `(city_id, date)` |
| `stg_latest_historical_daily` | `raw.historical_weather_daily` | `(city_id, date)` |

### Aggregation Views (2)

These views roll up deduplicated hourly data into daily summaries.

| Model | Source | Aggregations |
|---|---|---|
| `stg_city_daily_weather` | `stg_latest_weather_hourly` | AVG/MAX/MIN temp, SUM precip, MAX wind, MAX weather code |
| `stg_city_daily_air_quality` | `stg_latest_air_quality_hourly` | AVG/MAX AQI, AVG PM2.5/PM10/NO₂/O₃ |

### Unified Signal Table (1)

| Model | Description |
|---|---|
| `stg_city_signal_input` | Joins weather + air quality + river + historical into one row per `(city_id, date)` |

**Nullability rules:**
- Weather & air quality columns: always populated (all cities, daily)
- `river_discharge_m3s`: NULL for non-river-enabled cities (7 of 10)
- `hist_*` columns: NULL for dates outside the ERA5 lag window (most recent 6 days)

> **Note:** CMIP6 climate projections are intentionally excluded from `city_signal_input`. They have a different grain (10-year window, monthly refresh) and will be consumed separately in the mart layer as a long-term deviation baseline.

---

## Materialization

All staging models are materialized as **views** (not tables). This means:
- ✅ Zero storage cost
- ✅ Always fresh — reads from raw on every query
- ✅ No scheduled refresh needed
- ⚠️ Slightly slower queries (acceptable for silver; mart layer uses tables)

---

## Running the Models

### Via `make deploy` (recommended)

Staging views are created automatically as part of `make deploy`:

```
make deploy  →  build image  →  terraform apply  →  dbt run + test
```

No separate dbt command or profile configuration needed — the profile reads `GCP_PROJECT_ID` and `GCP_REGION` from your `.env` file automatically via dbt's `env_var()`.

### Prerequisites (first time only)

```bash
pip install -r transform/requirements.txt
gcloud auth application-default login
```

### Standalone Commands

| Command | Description |
|---|---|
| `make deploy` | Full pipeline: build + terraform + dbt run + test |
| `make dbt-stg` | Run staging models only |
| `make dbt-run` | Run all models (stg + mart) |
| `make dbt-test` | Run schema tests (not_null checks on key columns) |

### From the transform directory

```bash
cd transform
dbt run --profiles-dir . --select stg        # Build staging views
dbt test --profiles-dir . --select stg       # Run staging tests
dbt docs generate --profiles-dir . && dbt docs serve --profiles-dir .
```

---

## Schema Tests

The following tests are defined in `_stg_models.yml`:

| Model | Column | Test |
|---|---|---|
| All 7 models | `city_id` | `not_null` |
| Hourly models | `valid_ts_utc` | `not_null` |
| Daily models | `date` | `not_null` |
