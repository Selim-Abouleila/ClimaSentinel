# ClimaSentinel

ClimaSentinel is an automated climate data pipeline running on Google Cloud Platform. It ingests real-time weather, air quality, river discharge, historical ERA5 reanalysis, and long-term CMIP6 climate projections for 10 major European cities — every day, at zero marginal cost.

## Quick Start

```bash
git clone https://github.com/Selim-Abouleila/ClimaSentinel.git
cd ClimaSentinel
cp .env.example .env   # then fill in GCP_PROJECT_ID
```

**First time — initialise the Terraform state backend:**
```bash
make bootstrap
```

**Deploy GCP resources:**
```bash
make deploy
```

See the full guide in [docs/1-bootstrap-initialization.md](docs/1-bootstrap-initialization.md).

### All commands

| Command | Description |
|---|---|
| `make bootstrap` | Enable GCP APIs, create Artifact Registry repo, GCS state bucket, init Terraform |
| `make build` | Build & push the ingest Docker image via Cloud Build |
| `make deploy` | Full pipeline: build image + terraform apply + dbt run + dbt test |
| `make plan` | Dry run — show changes without applying |
| `make destroy` | Tear down all GCP resources |
| `make dbt-stg` | Run staging dbt models only |
| `make dbt-test` | Run dbt schema tests |

---

## Architecture

```mermaid
flowchart LR
    subgraph GCP["Google Cloud Platform"]
        direction LR
        SCH["☁️ Cloud Scheduler
        ─────────────
        cron: 0 6 * * *
        daily @ 06:00 UTC
        region: europe-west1"]

        CRJ["📦 Cloud Run Job
        ─────────────
        clima-sentinel-ingest
        region: europe-west9
        1 vCPU · 512 MB · 600s"]

        BQ_RAW["🗄️ BigQuery (Bronze)
        ─────────────
        raw.weather_forecast_hourly
        raw.air_quality_hourly
        raw.historical_weather_daily
        raw.flood_daily
        raw.climate_projections_daily"]

        DBT["⚙️ dbt (Transform)
        ─────────────
        Dedup, harmonize, aggregate
        Runs after Terraform apply"]

        BQ_STG["🗄️ BigQuery (Silver)
        ─────────────
        stg.stg_latest_*
        stg.stg_city_daily_*
        stg.stg_city_signal_input"]

        BQ_MART["🗄️ BigQuery (Gold)
        ─────────────
        mart.city_score_current
        mart.city_score_history
        mart.city_zone_current"]

        SCH -->|"HTTP POST (OAuth2)"| CRJ
        CRJ -->|"Streaming inserts"| BQ_RAW
        BQ_RAW --> DBT
        DBT -->|"Views"| BQ_STG
        DBT -->|"Tables"| BQ_MART
    end

    subgraph APIs["Open-Meteo APIs (Free · No API key)"]
        direction TB
        W["🌤️ Weather Forecast
        api.open-meteo.com/v1/forecast
        7 days · hourly"]

        AQ["🌫️ Air Quality
        air-quality-api.open-meteo.com
        5 days · hourly"]

        FL["🌊 River Discharge
        flood-api.open-meteo.com
        7 days · daily"]

        HW["📅 ERA5 Historical
        archive-api.open-meteo.com
        rolling 7-day window · daily"]

        CP["🌡️ CMIP6 Climate
        climate-api.open-meteo.com
        10-year projection · monthly"]
    end

    CITIES["📋 config/cities.csv
    10 European cities"]

    CITIES -->|"10 cities × 5 APIs"| CRJ
    W  --> CRJ
    AQ --> CRJ
    FL -->|"river_enabled cities only"| CRJ
    HW --> CRJ
    CP -->|"1st of month only"| CRJ
```

---

## Data Sources

| API | Endpoint | Grain | Rows/city/day | Table |
|---|---|---|---|---|
| Weather Forecast | `api.open-meteo.com/v1/forecast` | Hourly | 168 | `raw.weather_forecast_hourly` |
| Air Quality | `air-quality-api.open-meteo.com/v1/air-quality` | Hourly | 120 | `raw.air_quality_hourly` |
| River Discharge | `flood-api.open-meteo.com/v1/flood` | Daily | 7 | `raw.flood_daily` |
| ERA5 Historical | `archive-api.open-meteo.com/v1/archive` | Daily | 7 | `raw.historical_weather_daily` |
| CMIP6 Climate | `climate-api.open-meteo.com/v1/climate` | Daily | ~3,650/mo | `raw.climate_projections_daily` |

---

## BigQuery Datasets (Medallion Architecture)

| Layer | Dataset | Purpose | Key Tables | Status |
|---|---|---|---|---|
| 🥉 Bronze | `raw` | Raw API loads — append-only, partitioned by day | `weather_forecast_hourly`, `air_quality_hourly`, `flood_daily`, `historical_weather_daily`, `climate_projections_daily` | ✅ Live |
| 🥈 Silver | `stg` | Deduplicated, harmonized daily views (dbt) | `stg_latest_weather_hourly`, `stg_latest_air_quality_hourly`, `stg_latest_flood_daily`, `stg_latest_historical_daily`, `stg_city_daily_weather`, `stg_city_daily_air_quality`, `stg_city_signal_input` | ✅ Live |
| 🥇 Gold | `mart` | Tipping scores, city ranking, driver attribution | `city_score_current`, `city_score_history`, `city_zone_current` | 🔜 Next |

> **Bronze** tables are auto-created by the ingest job. **Silver** views are managed by dbt and deployed via `make deploy`. **Gold** marts are the next phase of development.

---

## Cities

| City | Country | Lat | Lon | River monitoring |
|---|---|---|---|---|
| Paris | FR | 48.853 | 2.348 | ✅ |
| London | GB | 51.508 | −0.125 | — |
| Madrid | ES | 40.416 | −3.702 | — |
| Berlin | DE | 52.524 | 13.410 | — |
| Rome | IT | 41.891 | 12.511 | — |
| Amsterdam | NL | 52.374 | 4.889 | ✅ |
| Athens | GR | 37.983 | 23.727 | — |
| Warsaw | PL | 52.229 | 21.011 | ✅ |
| Lisbon | PT | 38.716 | −9.133 | — |
| Stockholm | SE | 59.329 | 18.068 | — |

---

## Docs

| Document | Description |
|---|---|
| [1. Bootstrap Initialization](docs/1-bootstrap-initialization.md) | How to clone this project in GCP Cloud Shell and initialize the Terraform remote state backend |
| [2. Ingestion Pipeline](docs/2-ingestion-pipeline.md) | Details on the Cloud Run and BigQuery pipeline architecture and the 5 Open-Meteo APIs fetched |
| [3. Staging Layer](docs/3-staging-layer.md) | Silver layer: dbt deduplication, daily aggregation, and the unified `city_signal_input` view |