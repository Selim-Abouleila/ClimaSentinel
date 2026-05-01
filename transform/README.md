# ClimaSentinel — dbt Transform Layer

This directory contains the **dbt project** that transforms raw ingested data (Bronze) into clean staging views (Silver) and analytics marts (Gold) in BigQuery.

## Quick Start

### 1. Install dbt

```bash
pip install -r transform/requirements.txt
```

### 2. Authenticate with GCP

```bash
gcloud auth application-default login
```

### 3. Run via Makefile (recommended)

dbt is integrated into `make deploy` — no separate dbt command needed. The profile reads `GCP_PROJECT_ID` and `GCP_REGION` directly from your `.env` file via dbt's `env_var()`.

```bash
make deploy     # Build image → terraform apply → dbt run + test
make dbt-stg    # Run staging models only (standalone)
make dbt-test   # Run schema tests only (standalone)
```

### 4. Run standalone (from transform/)

```bash
cd transform
dbt run --profiles-dir .          # Build all models
dbt run --profiles-dir . -s stg   # Staging only
dbt test --profiles-dir .         # Schema tests
dbt docs generate --profiles-dir . && dbt docs serve --profiles-dir .
```

> **Note:** `--profiles-dir .` tells dbt to read `profiles.yml` from this directory instead of `~/.dbt/`. The profile uses `env_var('GCP_PROJECT_ID')` to read your project ID from the environment (exported by the Makefile from `.env`).

---

## Project Structure

```
transform/
├── dbt_project.yml                  # dbt project configuration
├── profiles.yml                     # BigQuery profile (reads from .env via env_var)
├── requirements.txt                 # Python deps (dbt-core + dbt-bigquery)
├── models/
│   └── stg/                         # Silver layer — staging views
│       ├── _stg_sources.yml         # Source definitions (raw.* tables)
│       ├── _stg_models.yml          # Model docs + schema tests
│       ├── stg_latest_weather_hourly.sql
│       ├── stg_latest_air_quality_hourly.sql
│       ├── stg_latest_flood_daily.sql
│       ├── stg_latest_historical_daily.sql
│       ├── stg_city_daily_weather.sql
│       ├── stg_city_daily_air_quality.sql
│       └── stg_city_signal_input.sql     ← ⭐ Unified input for mart layer
├── macros/                          # (future) Shared SQL macros
├── seeds/                           # (future) Static lookup CSVs
├── snapshots/                       # (future) SCD Type-2 snapshots
└── tests/                           # (future) Custom data tests
```

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

## Materialization Strategy

| Layer | Materialization | Rationale |
|---|---|---|
| `stg` (Silver) | **View** | Always fresh, zero storage cost, reads from raw on query |
| `mart` (Gold) | **Table** | Precomputed for dashboard performance |
