# ClimaSentinel

<div align="center">
  <img src="docs/images/ClimaSentinel_Theme_Picture.png" alt="ClimaSentinel Theme" width="600">
</div>

**🌍 Live Dashboard:** [climasentinel.up.railway.app](https://climasentinel.up.railway.app/)

ClimaSentinel is an automated climate data pipeline running on Google Cloud Platform. It ingests real-time weather, air quality, river discharge, historical ERA5 reanalysis, and long-term CMIP6 climate projections for 10 major European cities — every day, at zero marginal cost.


---

## Team

| Role | Members | Main Mission | Tools |
|---|---|---|---|
| **DE1 / Lead** | Selim Abouleila | Terraform, deployments, integration, unblocking issues | GitHub, Terraform, Cloud Run, BigQuery |
| **DE2** | Anaïs Robert | Ingestion code and raw data modelling | Python, Cloud Run, BigQuery |
| **DA1** | Begum Sozer, Rhita Moum, Nathan Germany | Scoring logic, datamart tables (business layer), dashboard | BigQuery SQL, Power BI, Streamlit |
| **DA2** | Nathan Germany, Xan Doyhenart | Data validation, quality checks, Monday docs & deliverables | BigQuery SQL, Power BI, Streamlit, docs, spreadsheets |

---

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
        stg.city_monthly_normals (seed)
        stg.stg_latest_*
        stg.stg_city_daily_*
        stg.stg_city_signal_input
        stg.stg_city_signal_vintage"]

        BQ_MART["🗄️ BigQuery (Gold)
        ─────────────
        mart.mart_city_score_current
        mart.mart_city_score_history
        mart.mart_city_zone_current
        mart.mart_city_score_detail
        mart.mart_ml_training_examples
        mart.mart_ml_serving_features_current"]

        SCH -->|"HTTP POST (OAuth2)"| CRJ
        CRJ -->|"Streaming inserts"| BQ_RAW
        BQ_RAW --> DBT
        DBT -->|"Views"| BQ_STG
        DBT -->|"Tables + Views"| BQ_MART
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

    subgraph SERVING["Serving Layer (Railway)"]
        direction TB
        BACKEND["🚀 Backend API
        ─────────────
        FastAPI · Railway
        /data/current-scores
        /data/city/·/scores
        /data/city/·/forecast
        GET /metrics (Prometheus)"]

        FRONTEND["🖥️ Frontend Dashboard
        ─────────────
        Next.js · Glassmorphism UI
        climasentinel.up.railway.app"]
    end

    subgraph MLOPS["MLOps Pipeline"]
        direction TB
        ML["🤖 ML Model
        ─────────────
        6-output Heat/Rain Random Forest
        Wind/AQ/River forecast rules
        MLflow + DagsHub registry
        model/train.py"]
    end

    subgraph MON["Monitoring"]
        direction TB
        PROM["📊 Prometheus
        ─────────────
        Scrapes /metrics
        Port 9090"]

        GRAF["📈 Grafana
        ─────────────
        Dashboards
        Port 3000"]

        PROM --> GRAF
    end

    CITIES["📋 config/cities.csv
    10 European cities"]

    NORMALS["🌱 transform/seeds/city_monthly_normals.csv
    10-year historical baselines"]

    CITIES -->|"10 cities × 5 APIs"| CRJ
    NORMALS -->|"dbt seed"| BQ_STG
    W  --> CRJ
    AQ --> CRJ
    FL -->|"river_enabled cities only"| CRJ
    HW --> CRJ
    CP -->|"1st of month only"| CRJ
    BQ_MART -->|"Current exact-vintage features"| BACKEND
    BACKEND -->|"REST API (JSON)"| FRONTEND
    BQ_MART -->|"Point-in-time training examples"| ML
    ML -->|"Pinned MLflow version"| BACKEND
    PROM -->|"Scrapes /metrics"| BACKEND
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
| 🥈 Silver | `stg` | Static seeds, operational daily views, and exact forecast vintages (dbt) | `city_monthly_normals`, `stg_latest_*`, `stg_city_signal_input`, `stg_city_signal_vintage` | ✅ Live |
| 🥇 Gold | `mart` | Operational scores plus point-in-time-safe ML training and serving contracts | `mart_city_score_history`, `mart_city_score_current`, `mart_ml_training_examples`, `mart_ml_serving_features_current` | ✅ Live |

> **Bronze** tables are auto-created by the ingest job. **Silver** and **Gold** models are managed by dbt and deployed via `make deploy`.

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

## CI/CD Pipeline & Model Promotion

ClimaSentinel uses a strict 4-tier branching strategy (`feature/*` → `dev` → `staging` → `main`) enforced by GitHub Actions to ensure code quality and safe MLOps deployments:

1. **Continuous Integration (`dev`):** Runs the full Python `pytest` suite (unit + integration tests) and verifies Docker builds.
2. **Staging Environment (`staging`):** Extracts a point-in-time snapshot, trains the six-output realized Heat/Rain model, gates and aliases its exact registry version, deploys it to Railway, then runs **Playwright E2E tests** against all three horizons and the hybrid API contract.
3. **Model Promotion & Production (`main`):** Repeats the provenance and quality gates before moving the exact candidate version. Learned Heat/Rain outputs require **R² ≥ 0.35**; aggregate horizon MAE must be ≤ 7, with component limits of 10 for Heat and 7 for Rain. Wind, AQ and River are excluded from model metrics because they remain explicitly unvalidated forecast-rule indicators.

*For full details on our pipelines and quality gates, please see [Doc 7: CI/CD and Branching Strategy](docs/7-cicd-and-branching.md).*

---

## Reproducibility

This project is built to be 100% reproducible from end-to-end:
- **Infrastructure:** All Google Cloud resources (BigQuery, Cloud Run, Scheduler) are defined in Infrastructure-as-Code using Terraform. Follow the [Quick Start](#quick-start) to recreate the environment.
- **Data Transformations:** The entire Medallion Architecture (Bronze → Silver → Gold) is generated reproducibly using `dbt`.
- **Machine Learning:** Data snapshots are versioned with **DVC**, and every model training run is tracked via **MLflow**, ensuring exact hyperparameter and metric reproducibility.

*For details on reproducing the ML pipelines or testing, refer to [Doc 11: Machine Learning Model](docs/11-machine-learning-model.md) and [Doc 13: End-to-End Testing](docs/13-end-to-end-testing.md).*

---

## Docs

| Document | Description |
|---|---|
| [1. Bootstrap Initialization](docs/1-bootstrap-initialization.md) | How to clone this project in GCP Cloud Shell and initialize the Terraform remote state backend |
| [2. Ingestion Pipeline](docs/2-ingestion-pipeline.md) | Details on the Cloud Run and BigQuery pipeline architecture and the 5 Open-Meteo APIs fetched |
| [3. Staging Layer](docs/3-staging-layer.md) | Silver layer: operational latest views plus exact-run weather, AQ, flood and unified signal vintages |
| [4. Mart Layer](docs/4-mart-layer.md) | Gold layer: operational scores plus point-in-time-safe ML feature, realized-label, training, and serving marts |
| [5. Guide Power BI](docs/5-guide-powerbi.md) | Guide en français pour connecter Power BI Desktop aux tables `mart` et configurer le rafraîchissement automatique |
| [6. Guide Streamlit](docs/6-guide-streamlit.md) | Guide en français pour créer un dashboard Python Streamlit connecté à BigQuery avec le même compte de service |
| [7. CI/CD and Branching Strategy](docs/7-cicd-and-branching.md) | Explanation of the strict Git branching model and the GitHub Actions deployment pipelines |
| [8. Backend Architecture](docs/8-backend.md) | FastAPI, exact-vintage serving, MLflow model pinning, forecast rules, and Dockerization |
| [9. Frontend Architecture](docs/9-frontend.md) | Next.js dashboard and transparent learned-versus-rule forecast presentation |
| [10. Monitoring Dashboard](docs/10-monitoring-dashboard.md) | Prometheus + Grafana observability stack: metrics scraping, dashboards, and Docker Compose setup |
| [11. Machine Learning Model](docs/11-machine-learning-model.md) | Six-output realized Heat/Rain model, purged validation, hybrid serving, MLflow, and DagsHub registry |
| [12. API Swagger Documentation](docs/12-api-swagger-documentation.md) | Interactive Swagger UI reference for all FastAPI endpoints, request/response schemas, and examples |
| [13. End-to-End Testing](docs/13-end-to-end-testing.md) | Details on Playwright E2E test suite running in staging CI pipeline |
