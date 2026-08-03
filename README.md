# ClimaSentinel

<div align="center">
  <img src="docs/images/ClimaSentinel_Theme_Picture.png" alt="ClimaSentinel Theme" width="600">
  <br>
  <sub>Illustrative project artwork; not live forecast evidence.</sub>
</div>

**🌍 Live Dashboard:** [climasentinel.up.railway.app](https://climasentinel.up.railway.app/)

ClimaSentinel combines a serverless GCP climate-data pipeline with a FastAPI
and Next.js serving layer on Railway. It ingests daily weather and air-quality
forecasts plus lagged Open-Meteo archive/reanalysis weather for 20 major
European cities, with river-discharge forecasts enabled for five of them,
transforms the data with BigQuery and dbt, and supports an optional monthly
CMIP6 projection source that is currently disabled in scheduled ingestion. The
operational dashboard path covers all 20 cities once the expanded data plane
and serving release are current; the beta forecast path remains intentionally
frozen to its original 10-city allowlist. Operational factors preserve missing
inputs as NULL, distinguish `unavailable` from `not_monitored`, expose input
coverage, and calculate each city score only from available factors.

The v2 API carries the selected operational run ID/timestamp; overview/detail
pages show that snapshot, warn after 36 hours, and flag scored cities with
partial factor coverage. This is visibility rather than a completed-run audit:
the pipeline does not yet persist a durable run manifest.

> **Forecasting is beta.** The three-day page presents experimental Day +1/+2/+3 point estimates from deterministic same-vintage rules, not a deployed ML model. Heat has limited backtest evidence against Open-Meteo archive/reanalysis data; Rain was backtested against the same source but showed insufficient skill; Wind, Air Quality and River are not observation-validated. Missing inputs remain unavailable, and no confidence intervals are claimed.

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

> **BigQuery prerequisite.** Terraform does not create the BigQuery `raw`
> dataset. Create it once as described in
> [Doc 1](docs/1-bootstrap-initialization.md); `make deploy` then validates the
> city files, applies Terraform, executes and waits for the ingestion job, and
> finishes with dbt seed/run/test.

```bash
git clone https://github.com/Selim-Abouleila/ClimaSentinel.git
cd ClimaSentinel
cp .env.example .env   # then fill in GCP_PROJECT_ID
```

**First time — initialise the Terraform state backend:**
```bash
make bootstrap
```

**Review the Terraform plan, then deploy the initialized environment:**
```bash
make plan
make deploy
```

`make deploy` updates the GCP ingestion/dbt pipeline only. It does not publish
the FastAPI or Next.js services on Railway; promote the reviewed commit from
`dev` to `staging` to run the repository's Railway deployment workflow.

For the availability-contract rollout, run `make deploy` first so the new v2
relations exist while the unsuffixed rollback relations remain live. Staging
then queues the backward-compatible frontend asynchronously and checks the v2
schemas, 20-city coverage, selected-run coherence and 36-hour snapshot age
while Railway builds it. The workflow next confirms the frontend's exact
commit/run marker under a strict 10-minute deadline and only then queues the v2
backend. A second bounded gate polls the frontend's no-cache backend-health
proxy until the backend reports the same exact release ID before E2E starts.

See the full guide in [docs/1-bootstrap-initialization.md](docs/1-bootstrap-initialization.md).

### All commands

| Command | Description |
|---|---|
| `make bootstrap` | Enable GCP APIs, create Artifact Registry repo, GCS state bucket, init Terraform |
| `make build` | Build & push the ingest Docker image via Cloud Build |
| `make validate-cities` | Validate the operational registry, 12 monthly normals per active city, signal-monitoring contract, and frozen forecast-city contract |
| `make deploy` | Validate city files, build/push, apply Terraform, execute and wait for ingestion, then run dbt seed/run/test |
| `make plan` | Dry run — show changes without applying |
| `make destroy` | Destroy Terraform-managed resources only; it does not remove the state bucket, Artifact Registry/images, BigQuery data, enabled APIs, or other imperatively created resources |
| `make dbt-stg` | Run staging dbt models only |
| `make dbt-test` | Run dbt schema and singular data tests |

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
        1 vCPU · 512 MB · 1200s"]

        BQ_RAW["🗄️ BigQuery (Bronze)
        ─────────────
        raw.weather_forecast_hourly
        raw.air_quality_hourly
        raw.historical_weather_daily
        raw.flood_daily
        raw.climate_projections_daily (optional)"]

        DBT["⚙️ dbt (Transform)
        ─────────────
        Dedup, harmonize, aggregate
        Runs after ingestion"]

        BQ_STG["🗄️ BigQuery (Silver)
        ─────────────
        stg.city_monthly_normals (seed)
        stg.city_signal_monitoring (seed)
        stg.forecast_city_allowlist (seed)
        stg.stg_operational_run_v2
        stg.stg_city_daily_*_v2
        stg.stg_city_signal_input_v2
        stg.stg_city_signal_vintage"]

        BQ_MART["🗄️ BigQuery (Gold)
        ─────────────
        mart.mart_city_score_history_v2
        mart.mart_city_score_current_v2
        mart.mart_city_score_detail_v2
        mart.mart_city_zone_current_v2
        mart.mart_ml_forecast_features_vintage
        mart.mart_city_realized_weather_daily
        mart.mart_ml_training_examples
        mart.mart_ml_serving_features_current"]

        SCH -->|"HTTP POST (OAuth2)"| CRJ
        CRJ -->|"Streaming inserts"| BQ_RAW
        BQ_RAW --> DBT
        DBT -->|"Views + selected-run table"| BQ_STG
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

        HW["📅 Historical Weather / Reanalysis
        archive-api.open-meteo.com
        rolling 7-day window · daily"]

        CP["🌡️ CMIP6 Climate
        climate-api.open-meteo.com
        10-year daily projection
        optional · scheduled fetch off"]
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
        ML["🧪 ML Challenger
        ─────────────
        6-output Heat/Rain Random Forest
        Offline baseline comparison
        MLflow + DagsHub registry
        model/train.py"]
    end

    subgraph MON["Monitoring"]
        direction TB
        PROM["📊 Local Prometheus demo
        ─────────────
        Scrapes /metrics
        Port 9090"]

        GRAF["📈 Local Grafana demo
        ─────────────
        Dashboard · no alert rules
        Port 3000"]

        PROM --> GRAF
    end

    CITIES["📋 config/cities.csv
    20 operational cities"]

    NORMALS["🌱 transform/seeds/city_monthly_normals.csv
    240-row monthly baseline lookup"]

    FORECAST_SCOPE["🌱 transform/seeds/forecast_city_allowlist.csv
    Original 10-city forecast contract"]

    CITIES -->|"20 cities: weather + AQ + archive; river for 5"| CRJ
    NORMALS -->|"dbt seed"| BQ_STG
    FORECAST_SCOPE -->|"dbt seed"| BQ_STG
    W  --> CRJ
    AQ --> CRJ
    FL -->|"river_enabled cities only"| CRJ
    HW --> CRJ
    CP -.->|"optional integration"| CRJ
    BQ_MART -->|"20-city operational scores + 10-city exact-vintage forecast features"| BACKEND
    BACKEND -->|"REST API (JSON)"| FRONTEND
    BQ_MART -->|"Point-in-time training examples"| ML
    PROM -->|"Scrapes /metrics"| BACKEND
```

---

## Data Sources

| API | Endpoint | Grain | Typical rows/city/run | Table |
|---|---|---|---|---|
| Weather Forecast | `api.open-meteo.com/v1/forecast` | Hourly | 168 | `raw.weather_forecast_hourly` |
| Air Quality | `air-quality-api.open-meteo.com/v1/air-quality` | Hourly | 120 | `raw.air_quality_hourly` |
| River Discharge | `flood-api.open-meteo.com/v1/flood` | Daily | 7 | `raw.flood_daily` |
| Historical Weather / Reanalysis | `archive-api.open-meteo.com/v1/archive` | Daily | 7 | `raw.historical_weather_daily` |
| CMIP6 Climate (integration present; scheduled fetch disabled; no mart consumer) | `climate-api.open-meteo.com/v1/climate` | Daily | ~3,650 when invoked | `raw.climate_projections_daily` |

The hourly weather and air-quality timestamps are provider-local clock values
stored in a field named `valid_ts_utc`; no source offset is retained. Do not use
that field for exact absolute lead-time or DST auditing. Daily staging currently
preserves the encoded local calendar label, while the operational current marts
filter two UTC date labels. That behavior neither corrects the underlying
timestamp nor creates a rolling 48-hour window.

The scheduled historical fetch currently calls the Open-Meteo Archive API
without pinning a `models=era5` selector and does not persist returned
source-model metadata. The `era5_*` validation-status names, the
`label_source='open_meteo_era5'` value and existing beta copy are retained
legacy API/product contract labels; they must not be treated as per-row proof
of an exact reanalysis model/version.

---

## BigQuery Datasets (Medallion Architecture)

| Layer | Dataset | Purpose | Key Tables | Status |
|---|---|---|---|---|
| 🥉 Bronze | `raw` | Raw API loads — append-only, partitioned by day | Active: `weather_forecast_hourly`, `air_quality_hourly`, `flood_daily`, `historical_weather_daily`; optional: `climate_projections_daily` | Configured; dataset existence and freshness require runtime verification |
| 🥈 Silver | `stg` | Static seeds, exact-run operational inputs, and exact forecast vintages (dbt) | `city_monthly_normals`, `city_signal_monitoring`, `forecast_city_allowlist`, `stg_operational_run_v2`, `stg_city_daily_weather_v2`, `stg_city_daily_air_quality_v2`, `stg_flood_daily_v2`, `stg_city_signal_input_v2`, `stg_city_signal_vintage` | dbt-managed; deployment and freshness require runtime verification |
| 🥇 Gold | `mart` | Availability-aware operational scores, exact-vintage forecast features, and archive/reanalysis-backed Heat/Rain labels | `mart_city_score_history_v2`, `mart_city_score_current_v2`, `mart_city_score_detail_v2`, `mart_city_zone_current_v2`, `mart_ml_forecast_features_vintage`, `mart_city_realized_weather_daily`, `mart_ml_training_examples`, `mart_ml_serving_features_current` | dbt-managed; deployment and freshness require runtime verification |

The four unsuffixed operational marts (`mart_city_score_history`,
`mart_city_score_current`, `mart_city_score_detail` and
`mart_city_zone_current`) are temporary legacy rollback compatibility only.
They retain their legacy schema and missing-as-zero behavior; v2 availability
columns must not be inferred from them.

> The ingest job creates active-source **Bronze tables only after the `raw`
> dataset exists**. **Silver** and **Gold** models are managed by dbt. Source
> partial failures and embedded dbt failures propagate as a failed Cloud Run
> execution. Scheduled runs do not execute `dbt test`; `make deploy` adds a
> final dbt seed/run/test after the ingestion job completes.

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
| Vienna | AT | 48.208 | 16.374 | ✅ |
| Brussels | BE | 50.850 | 4.352 | — |
| Copenhagen | DK | 55.676 | 12.568 | — |
| Dublin | IE | 53.350 | −6.260 | — |
| Oslo | NO | 59.914 | 10.752 | — |
| Helsinki | FI | 60.170 | 24.938 | — |
| Prague | CZ | 50.076 | 14.438 | — |
| Budapest | HU | 47.498 | 19.040 | ✅ |
| Zurich | CH | 47.377 | 8.542 | — |
| Bucharest | RO | 44.427 | 26.103 | — |

All 20 active configured cities are intended to feed the operational
current-score and city-detail marts after successful ingestion and dbt refresh.
Vienna, Brussels, Copenhagen, Dublin, Oslo, Helsinki, Prague, Budapest, Zurich
and Bucharest are deliberately absent from `forecast_city_allowlist.csv`; they
do not enter forecast-vintage features, ML training, forecast serving, or the
forecast page's original 10-city selector.

### Operational city onboarding

Operational coverage is registry-driven rather than implemented with one
pipeline per city. An active city requires one reviewed `config/cities.csv`
record, exactly 12 approved rows in `city_monthly_normals.csv`, a row in
`city_signal_monitoring.csv`, and a deliberate `river_enabled` decision. The
expansion cohort added 10 registry/monitoring records and 120 monthly-baseline
rows, bringing the checked-in contracts to 20 operational cities, 20 monitoring
rows and 240 city-month rows. The normals generator and provenance manifest
record the expansion's 2014–2023 Open-Meteo procedure without silently
refreshing the original 10 cities' retained values.

Run `make validate-cities` before building or deploying. It checks schemas,
identifiers, coordinates, IANA time-zone names, display order, strict booleans,
physical ranges, city/month completeness, the provenance checksum/count
contract, monitoring-seed membership and exact River alignment with
`river_enabled`, plus the separate frozen forecast allowlist. Expanding
operational coverage does **not** expand the beta forecast path; that requires
an explicit, separately reviewed change to the allowlist, the independent
backend model-city vocabulary, training and serving contracts, the frontend
selector and their tests.

---

## CI/CD Pipeline & Model Promotion

ClimaSentinel documents a four-tier branching strategy (`feature/*` → `dev` →
`staging` → `main`) and validates it with GitHub Actions. Branch protection is
configured outside the repository and must be verified in GitHub:

1. **PR validation (`dev`):** Validates the city registry, normals, monitoring and forecast-scope contracts; unit-tests ingestion failure propagation and backend v2 response invariants; performs a credential-free `dbt parse`; runs frontend lint, availability/health-proxy unit tests and build; and builds both backend and ingestion Docker images.
2. **Staging environment (`staging`):** After `make deploy` has created the v2 relations alongside legacy rollback marts, extracts a point-in-time snapshot and evaluates the six-output Heat/Rain challenger. It then uses a pinned Railway CLI to queue the compatibility frontend with `--detach`, runs the v2 schema/city/run/age gate while Railway builds it, and confirms its exact release marker with a bounded poll. Only after both gates pass does it queue the v2 backend. The backend is accepted only when `/api/backend-health` reports `healthy` with the exact same commit/run release ID; Chromium E2E then covers Paris forecasts and Stockholm's unmonitored River state. Frontend and backend cutovers are deliberately not parallel. Training jobs do not currently receive GitHub Environment isolation, and staging promotion can move the shared MLflow `Production` stage/`champion` alias.
3. **Production gate (`main`):** A candidate must have non-negative component R², beat the exact matching rule MAE by at least 5%, and satisfy horizon-aware absolute MAE ceilings. Authentication, provenance or artifact-contract failures remain fatal. Railway production deployment is currently disabled, and the operational response continues to serve all five same-vintage rules without model intervals.

PR and staging CI do not currently exercise source fetchers, BigQuery loader
writes, or an authenticated `dbt run`/`dbt test`. PR CI does parse the dbt graph
without warehouse credentials, while the staging readiness gate validates the
already-deployed v2 relations; see [Doc 7](docs/7-cicd-and-branching.md) for the
tested boundaries.

*For full details on our pipelines and quality gates, please see [Doc 7: CI/CD and Branching Strategy](docs/7-cicd-and-branching.md).*

---

## Reproducibility

The repository contains the main ingredients for traceable runs, with important
current limits:

- **Infrastructure:** Cloud Run, Scheduler, service accounts and IAM are in
  Terraform. The state bucket, Artifact Registry and `raw` dataset lifecycle are
  outside that state, so Quick Start is not a complete clean-room recreation.
- **Data transformations:** dbt defines Silver and Gold, but requires initialized
  Bronze sources and successful credentials/source access. All 240 monthly
  normals rows are structurally validated. The new cities' 120 rows have a
  checked-in generator and provenance manifest for their 2014–2023 Open-Meteo
  procedure; the retained legacy 120 rows predate that generator and are not
  claimed to be exactly reproducible from a provider dataset that can change.
- **Machine learning:** MLflow records runs, but the DVC pointer on the current
  `dev` line is a legacy snapshot that predates the schema-v3 six-output
  training contract. Workflow-generated pointer commits are branch-local, so
  inspect the exact revision being run. `dvc pull` alone does not reproduce the
  current challenger from `dev`; regenerate and version a compatible snapshot
  before claiming exact reproduction.

*For details on reproducing the ML pipelines or testing, refer to [Doc 11: Machine Learning Model](docs/11-machine-learning-model.md) and [Doc 13: End-to-End Testing](docs/13-end-to-end-testing.md).*

---

## Docs

| Document | Description |
|---|---|
| [1. Bootstrap Initialization](docs/1-bootstrap-initialization.md) | How to clone this project in GCP Cloud Shell and initialize the Terraform remote state backend |
| [2. Ingestion Pipeline](docs/2-ingestion-pipeline.md) | Cloud Run and BigQuery ingestion architecture, source contracts, and fetch cadences |
| [3. Staging Layer](docs/3-staging-layer.md) | Silver layer: exact-run availability-aware operational inputs plus point-in-time-safe forecast vintages |
| [4. Mart Layer](docs/4-mart-layer.md) | Gold layer: active v2 operational scores, temporary legacy rollback marts, and ML feature/label marts |
| [5. Guide Power BI](docs/5-guide-powerbi.md) | Guide en français pour connecter Power BI Desktop aux tables `mart` et configurer le rafraîchissement automatique |
| [6. Guide Streamlit](docs/6-guide-streamlit.md) | Guide en français pour connecter Streamlit à BigQuery avec une identité dédiée et des secrets gérés |
| [7. CI/CD and Branching Strategy](docs/7-cicd-and-branching.md) | Intended branch flow, GitHub Actions behavior, secret scope, and current deployment/registry limitations |
| [8. Backend Architecture](docs/8-backend.md) | FastAPI, exact-vintage rule serving, offline challenger boundary, and Dockerization |
| [9. Frontend Architecture](docs/9-frontend.md) | Next.js dashboard, beta rule-forecast UI, and transparent validation presentation |
| [10. Monitoring Dashboard](docs/10-monitoring-dashboard.md) | Local Prometheus + Grafana observability demo, its metric semantics, and production gaps |
| [11. Machine Learning Model](docs/11-machine-learning-model.md) | Six-output realized Heat/Rain challenger, purged validation, rule baselines, MLflow, and DagsHub registry |
| [12. API Swagger Documentation](docs/12-api-swagger-documentation.md) | FastAPI endpoint reference and typed availability-aware operational and forecast contracts |
| [13. End-to-End Testing](docs/13-end-to-end-testing.md) | Exact frontend/backend release-gated staging E2E plus local availability unit-test coverage |
| [Archived project material](docs/archive/README.md) | Dated, superseded project artifacts retained with provenance and use restrictions |
