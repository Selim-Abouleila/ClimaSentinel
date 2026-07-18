# 3. Staging Layer (Silver)

The staging layer transforms raw, append-only ingested data into clean, deduplicated, and harmonized views in BigQuery. It uses **dbt** (data build tool) to manage SQL transformations with dependency ordering, schema tests, and auto-generated documentation.

## Purpose

The `raw.*` tables accumulate overlapping data on every ingestion run (e.g., 168 hourly weather rows per city per day, with 6 days of overlap between consecutive runs). The layer now exposes two intentionally different paths: the existing `stg_latest_*` path supports the operational dashboard, while the parallel `*_vintage` path preserves what was available at each ingestion run for point-in-time ML training and serving.

Before computing operational tipping scores, we need to:

1. **Deduplicate** — Keep only the freshest forecast for each `(city_id, timestamp)` pair
2. **Handle nulls** — Coalesce missing sensor readings to avoid downstream errors
3. **Harmonize grain** — Roll hourly tables down to daily summaries so all signals share the same `(city_id, date)` key
4. **Unify** — JOIN all signals into a single `stg.city_signal_input` table for the mart layer

For point-in-time ML inputs, we instead:

1. **Preserve forecast runs** — Retain `ingestion_run_id` and `ingested_at_utc`
2. **Aggregate within a run** — Never mix forecast revisions in one daily row
3. **Use exact calendar horizons** — Derive `horizon_days` with `DATE_DIFF`
4. **Preserve missingness** — Keep NULL measurements and expose reading counts
5. **Join coherently** — Join weather, AQ, and flood only from the exact same run

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

raw.weather_forecast_hourly ──→ stg_weather_forecast_hourly_vintage ──→ stg_city_daily_weather_vintage ──┐
raw.air_quality_hourly ────────→ stg_air_quality_hourly_vintage ───────→ stg_city_daily_air_quality_vintage ┤
raw.flood_daily ───────────────→ stg_flood_daily_vintage ──────────────────────────────────────────────────┤
                                                                                                           ▼
                                                                                         stg_city_signal_vintage
                                                                                         (future ML marts)
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

### Forecast-Vintage Views (6)

These views preserve every ingestion run. `ingested_at_utc` is the ingestion-run start timestamp used as ClimaSentinel's availability proxy; it is not Open-Meteo's model issue or initialization timestamp.

| Model | Grain | Purpose |
|---|---|---|
| `stg_weather_forecast_hourly_vintage` | `(ingestion_run_id, city_id, valid_ts_utc)` | Retains every hourly weather forecast revision |
| `stg_city_daily_weather_vintage` | `(ingestion_run_id, city_id, valid_date)` | Aggregates weather inside one retrieval only |
| `stg_air_quality_hourly_vintage` | `(ingestion_run_id, city_id, valid_ts_utc)` | Retains every hourly AQ forecast revision |
| `stg_city_daily_air_quality_vintage` | `(ingestion_run_id, city_id, valid_date)` | Aggregates AQ inside one retrieval only |
| `stg_flood_daily_vintage` | `(ingestion_run_id, city_id, valid_date)` | Retains every river-discharge forecast revision |
| `stg_city_signal_vintage` | `(ingestion_run_id, city_id, valid_date)` | Same-run weather/AQ/flood signal view anchored on weather |

The vintage path does not join ERA5. ERA5 is published later and belongs to a future realized-outcome/label path, not to the forecast snapshot that was available at prediction time.

**Vintage nullability and coverage rules:**

- Missing measurements remain NULL; staging never turns missing AQ, rain, wind, or river values into zero.
- Per-variable reading counts and source-presence flags make partial responses observable.
- AQ and flood never fall back to a different run after a partial ingestion failure.
- Flood is legitimately absent for non-river-enabled cities.
- AQ has a five-day window while weather and flood have seven-day windows.

> **Timestamp caveat:** the current fetcher requests city-local timestamps and stores the offset-free strings in `valid_ts_utc`. The daily `valid_date` and `horizon_days` convention is usable at the current 06:00 UTC cadence, but precise lead-hour and DST calculations must wait for the separate ingestion timestamp correction.

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
dbt run --profiles-dir . --select tag:forecast_vintage
dbt test --profiles-dir . --select tag:forecast_vintage
dbt docs generate --profiles-dir . && dbt docs serve --profiles-dir .
```

---

## Schema Tests

Core schema tests are defined in `_stg_models.yml` and `_stg_vintage_models.yml`. Singular tests in `transform/tests` validate the composite vintage grains, origin/horizon derivation, one timestamp per run, and the weather-anchored unified key set. Coverage anomalies are warnings during the initial raw-history audit rather than filters or hard failures.

| Model | Column | Test |
|---|---|---|
| All 7 models | `city_id` | `not_null` |
| Hourly models | `valid_ts_utc` | `not_null` |
| Daily models | `date` | `not_null` |
| Vintage models | Lineage and grain columns | `not_null` |
| All vintage models | Composite run/city/valid key | Singular uniqueness test |
