# ClimaSentinel

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
| `make bootstrap` | Create GCS state bucket & init Terraform backend |
| `make deploy` | `terraform plan` + `terraform apply` |
| `make plan` | Dry run — show changes without applying |
| `make destroy` | Tear down all GCP resources |

---

## Architecture

```mermaid
flowchart LR
    subgraph GCP["Google Cloud Platform"]
        direction LR
        SCH["☁️ Cloud Scheduler\n─────────────\ncron: 0 6 * * *\n(daily @ 06:00 UTC)\nregion: europe-west1"]
        CRJ["📦 Cloud Run Job\n─────────────\nclima-sentinel-ingest\nregion: europe-west9\n1 vCPU · 512 MB · 600s"]
        BQ["🗄️ BigQuery\n─────────────\nraw.weather_forecast_hourly\nraw.air_quality_hourly\nPartitioned by day"]

        SCH -->|"HTTP POST\n(OAuth2)"| CRJ
        CRJ -->|"Streaming insert\n2,880 rows/day"| BQ
    end

    subgraph APIs["Open-Meteo APIs (Free, no key)"]
        W["🌤️ Weather Forecast\napi.open-meteo.com\n7 days · hourly\ntemp, precip, wind, code"]
        A["🌫️ Air Quality\nair-quality-api.open-meteo.com\n5 days · hourly\nAQI, PM2.5, PM10, NO₂, O₃"]
    end

    CITIES["📋 config/cities.csv\n10 European cities"]

    CITIES -->|"10 cities × 2 APIs"| CRJ
    W -->|"168 rows/city"| CRJ
    A -->|"120 rows/city"| CRJ
```

---

## Docs

| Document | Description |
|---|---|
| [1. Bootstrap Initialization](docs/1-bootstrap-initialization.md) | How to clone this project in GCP Cloud Shell and initialize the Terraform remote state backend |
| [2. Ingestion Pipeline](docs/2-ingestion-pipeline.md) | Details on the Cloud Run and BigQuery pipeline architecture and real-time APIs fetched |