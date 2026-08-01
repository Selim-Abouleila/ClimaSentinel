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

dbt is integrated into `make deploy`. The Makefile exports `.env`, after which
the profile reads `GCP_PROJECT_ID` and `GCP_REGION` from the process environment
through dbt's `env_var()`. dbt does not parse `.env` by itself.

```bash
make deploy     # Build/push → Terraform apply → dbt seed/run/test
make dbt-stg    # Run staging models only (standalone)
make dbt-test   # Run schema and singular tests (standalone)
```

`make deploy` is mutating and non-interactive: it builds and pushes an image,
immediately applies a saved Terraform plan, installs dbt dependencies, then runs
seed/model/test commands. Use `make plan` separately when you need to review the
Terraform diff before deployment.

On a clean project, the `raw` BigQuery dataset must be created first. The first
`make deploy` can apply infrastructure and then fail at dbt because the active
raw source tables do not exist until the ingestion job has run once. Follow the
clean-room sequence and IAM prerequisites in
[Doc 1](../docs/1-bootstrap-initialization.md).

### 4. Run standalone (from transform/)

```bash
cd transform
set -a
source ../.env
set +a
dbt run --profiles-dir .          # Build all models
dbt run --profiles-dir . -s stg   # Staging only
dbt test --profiles-dir .         # Schema and singular tests
dbt docs generate --profiles-dir . && dbt docs serve --profiles-dir .
```

> **Note:** `--profiles-dir .` tells dbt to read `profiles.yml` from this
> directory instead of `~/.dbt/`. The committed `dev` and `prod` outputs are
> currently identical; selecting `--target prod` does not create environment
> isolation. The active credentials and `GCP_PROJECT_ID` determine the project.

---

## Project Structure

```
transform/
├── dbt_project.yml                  # dbt project configuration
├── profiles.yml                     # BigQuery profile (reads exported environment)
├── requirements.txt                 # Python deps (dbt-core + dbt-bigquery)
├── models/
│   ├── stg/                         # Silver layer — staging views
│   │   ├── _stg_sources.yml         # Source definitions (raw.* tables)
│   │   ├── _stg_models.yml          # Model docs + schema tests
│   │   ├── _stg_vintage_models.yml  # Vintage model docs + schema tests
│   │   ├── stg_latest_weather_hourly.sql
│   │   ├── stg_latest_air_quality_hourly.sql
│   │   ├── stg_latest_flood_daily.sql
│   │   ├── stg_latest_historical_daily.sql
│   │   ├── stg_city_daily_weather.sql
│   │   ├── stg_city_daily_air_quality.sql
│   │   ├── stg_city_signal_input.sql     ← ⭐ Operational mart input
│   │   ├── stg_weather_forecast_hourly_vintage.sql
│   │   ├── stg_city_daily_weather_vintage.sql
│   │   ├── stg_air_quality_hourly_vintage.sql
│   │   ├── stg_city_daily_air_quality_vintage.sql
│   │   ├── stg_flood_daily_vintage.sql
│   │   └── stg_city_signal_vintage.sql   ← Point-in-time ML staging input
│   └── mart/                        # Gold — operational + 4 point-in-time ML marts + legacy feature table
├── macros/
│   └── generate_schema_name.sql      # Preserve explicit stg/mart datasets
├── seeds/
│   ├── _seeds.yml                    # Seed docs + schema tests
│   ├── city_monthly_normals.csv      # Static monthly climate baselines
│   └── forecast_city_allowlist.csv   # Forecast city + IANA timezone contract
└── tests/                           # Singular lineage, grain, and coverage tests
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
                                                                                        ├──→ mart_city_score_history
                                                                                                  ├──→ mart_city_score_current
                                                                                                  │          └──→ mart_city_zone_current
                                                                                                  └──→ mart_city_score_detail
                                                                                        └──→ mart_ml_feature_store (legacy)

raw.weather_forecast_hourly ──→ stg_weather_forecast_hourly_vintage ──→ stg_city_daily_weather_vintage ──┐
raw.air_quality_hourly ────────→ stg_air_quality_hourly_vintage ───────→ stg_city_daily_air_quality_vintage ┤
raw.flood_daily ───────────────→ stg_flood_daily_vintage ──────────────────────────────────────────────────┤
                                                                                                           ▼
                                                                                         stg_city_signal_vintage
                                                                                                   │
                                                                                                   ▼
                                                                              mart_ml_forecast_features_vintage
                                                                                     ├──→ mart_ml_serving_features_current
                                                                                     └──→ mart_ml_training_examples
                                                                                                   ▲
raw.historical_weather_daily ──→ stg_latest_historical_daily ──→ mart_city_realized_weather_daily ─────────┘
```

The vintage path keeps `ingestion_run_id` in its grain and joins sources only
within the same run. Each vintage entry model first joins
`forecast_city_allowlist`, which admits only the intentional forecast cities
and supplies `forecast_origin_time_zone`. The models derive
`forecast_origin_date` from the UTC ingestion timestamp in that timezone, so
late or manual runs retain the correct local Day `0–6` weather trajectory.
Operational dashboard cities absent from the seed do not enter point-in-time
forecast features, training or serving outputs. Realized-weather history and
the unused legacy feature table intentionally remain outside this filter.

The raw field named `valid_ts_utc` is currently populated from offset-free
city-local provider strings and must not be treated as a trustworthy UTC
instant for precise lead-hour or DST calculations. The vintage daily models
preserve missing measurements, while the legacy operational daily models
coalesce some missing precipitation, wind and pollutant readings to zero.

Vintage coverage is also literal: `has_24_hour_coverage` requires exactly 24
distinct stored timestamps. If an upstream DST-transition day contains 23 or
25, the flag is false and the Horizon 0-4 feature window is ineligible for
canonical training and serving. No timezone-aware 23/24/25-hour exception is
implemented.

Build and validate the vintage path independently with:

```bash
dbt build --profiles-dir . --select tag:forecast_vintage
```

The scheduled ingestion job runs `dbt seed` and `dbt run`, but not `dbt test`;
it can also appear successful after a logged dbt failure. Run tests explicitly
and inspect transform completion in the job logs.

The GitHub pull-request, staging and production workflows do not currently
compile or test this dbt project. `_stg_sources.yml` also has no configured
source-freshness policy. A green application CI run, a passing manual `dbt
test`, and recent raw data are therefore three separate checks.

## Static-Seed Provenance

`city_monthly_normals.csv` is a checked-in 120-row city/month lookup used by the
Heat rules and labels. Repository history describes it as derived from
2014-2023 Open-Meteo/ERA5 data, but no generation script/query, exact source
model/version, retrieval timestamp or missing-data rules are stored. The CSV is
version-controlled but not reproducible from this repository alone; record
those inputs before refreshing it and compare results against a pinned seed
commit or hash.

---

## Materialization Strategy

| Layer | Materialization | Rationale |
|---|---|---|
| `stg` (Silver) | **Views** | Queries current raw rows; definition changes still require `dbt run` |
| Gold history/features/labels/training | **Tables** | Full-refresh, precomputed relations |
| Gold current/detail/zone/serving selectors | **Views** | Current projections over the precomputed tables |
