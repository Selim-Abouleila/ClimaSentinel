# 7. CI/CD and Branching Strategy

This project adheres to a strict Git branching model and automated CI/CD pipelines to ensure code quality, isolated environments, and seamless deployments across development, staging, and production.

---

## Branching Model

We follow a four-tier branching strategy enforced through GitHub branch protection rules:

```
feature/* ──PR──▸ dev ──push──▸ staging ──push──▸ main
```

| Branch | Role | Trigger |
|---|---|---|
| `feature/*` | All active development. Developers branch off `dev`, implement changes, and open a PR back into `dev`. | Manual |
| `dev` | Integration branch. Merging features here validates they work together. | PR merge |
| `staging` | Pre-production validation. Code is deployed to a live staging environment on Railway for final testing. | Push (from dev merge) |
| `main` | Production. Only fully validated code and models are deployed here. | Push (from staging merge) |

---

## Automated CI/CD Pipelines

All pipelines are implemented as **GitHub Actions** workflows located in `.github/workflows/`.

### Pipeline 1 — PR to `dev` (`ci-dev.yml`)

**Trigger:** Pull request opened against the `dev` branch.

This pipeline is the first quality gate. It validates that new feature code doesn't break existing functionality and that the Docker image builds successfully.

| Step | Description |
|---|---|
| **Checkout code** | `actions/checkout@v4` |
| **Set up Python 3.11** | `actions/setup-python@v5` with pip caching from `backend/requirements.txt` |
| **Install dependencies** | `pip install -r requirements.txt` |
| **Run unit tests** | `pytest tests/ -v -k "not integration"` — runs all tests *not* marked as integration |
| **Run integration tests** | `pytest tests/ -v -m integration` — runs only tests marked `@pytest.mark.integration` |
| **Build Docker image** | `docker build -f backend/Dockerfile -t climasentinel-backend:test .` — verifies the image compiles but does **not** push to any registry |

> If any step fails, the PR is blocked from merging.

---

### Pipeline 2 — Push to `staging` (`ci-staging.yml`)

**Trigger:** Push to the `staging` branch (i.e., a PR from `dev` is merged).

This pipeline re-runs the full test suite, builds the Docker image, and deploys both the backend and frontend to the **staging environment** on Railway.

| Step | Description |
|---|---|
| **Full test suite** | `pytest tests/ -v` — runs *all* tests (unit + integration) to catch regressions |
| **Build Docker image** | Builds `climasentinel-backend:staging` |
| **Deploy backend to Railway** | Uses `railway up --environment staging` with service-specific secrets |
| **Deploy frontend to Railway** | Uses `railway up --environment staging` for the frontend service |
| **Deploy candidate model** | Deploys the latest candidate model version from the MLflow registry to the staging environment for validation |

**Railway secrets used:** `RAILWAY_TOKEN`, `RAILWAY_PROJECT_ID`, `RAILWAY_SERVICE_ID`, `RAILWAY_FRONTEND_SERVICE_ID` — all injected from the `staging` GitHub environment.

---

### Pipeline 3 — Push to `main` / Production (`ci-production.yml`)

**Trigger:** Push to the `main` branch (i.e., a PR from `staging` is merged).

This is the final deployment gate. It runs model promotion quality gates before deploying to production.

| Step | Description |
|---|---|
| **Model promotion gates** | Executes `model/promote.py` which connects to DagsHub MLflow, fetches the latest model metrics, and validates that **R2 >= 0.45** and **MAE <= 7.0**. If passed, the script automatically promotes the model to the `Production` stage in the registry. |
| **Deploy backend to Railway** | `railway up --environment production` — only runs if the quality gates pass. |
| **Deploy frontend to Railway** | `railway up --environment production` for the frontend service. |

> **Guard gate behavior:** If any quality gate fails, the deployment is aborted and the production environment remains unchanged. The model stays in `Staging` stage in the registry.

**Railway secrets used:** Same structure as staging, scoped to the `production` GitHub environment.

---

### Pipeline 4 — MLOps Training Pipeline (`ci-mlops.yml`)

**Trigger:** Push to `main` *or* manual dispatch (`workflow_dispatch`).

This pipeline handles the full ML lifecycle: data extraction, versioning, training, and model registration.

| Step | Description |
|---|---|
| **Checkout code** | With `contents: write` permission for auto-committing DVC files |
| **Set up Python 3.11** | Installs ML stack: `scikit-learn`, `mlflow`, `dagshub`, `dvc`, `pandas`, etc. |
| **Authenticate with GCP** | Uses `google-github-actions/auth@v2` with `GCP_SA_KEY` secret |
| **Configure DVC remote** | Sets up DagsHub DVC remote with basic auth (`DAGSHUB_USERNAME`, `DAGSHUB_TOKEN`) |
| **Extract data from BigQuery** | Runs `python model/extract_data.py` to snapshot the latest mart data |
| **Track with DVC & push** | `dvc add model/data/training_snapshot.csv` → `dvc push` to DagsHub storage |
| **Commit DVC version** | Auto-commits the updated `.dvc` file back to Git with `[skip ci]` to avoid infinite loops |
| **Validate MLflow secrets** | Checks that `MLFLOW_TRACKING_URI` is set before training |
| **Train & register model** | Runs `python -m model.train` which trains the shared multi-output preprocessing/model pipeline and registers it in the MLflow Model Registry on DagsHub |

**Every training run is traceable to:**
- A **DVC data version** (MD5 hash read from the `.dvc` metadata file)
- A **Git commit hash** (`git rev-parse HEAD`)

Both are logged as MLflow parameters alongside model metrics (`mse`, `mae`, `r2`) and hyperparameters.

---

## Testing Strategy

All tests are located in `backend/tests/` and run automatically in CI. The test suite uses **pytest** with the `@pytest.mark.integration` marker to separate test types.

### Unit Tests (3)

Unit tests validate isolated endpoint behavior using the FastAPI `TestClient` without external dependencies:

| Test | What it validates |
|---|---|
| `test_root_returns_service_info` | `GET /` returns correct service name and version |
| `test_health_returns_healthy` | `GET /health` returns `{"status": "healthy"}` |
| `test_health_contains_uptime` | `GET /health` includes a non-negative `uptime_seconds` field |

### Mock Data Tests (3)

These tests use `unittest.mock.patch` to mock the BigQuery client and validate endpoint logic in isolation:

| Test | What it validates |
|---|---|
| `test_get_current_scores_mocked` | `/data/current-scores` correctly parses and returns mocked BigQuery rows |
| `test_get_city_scores_not_found` | `/data/city/{id}/scores` returns `404` when BigQuery returns empty results |
| `test_get_history_scores_db_error` | `/data/history-scores` returns a clean `500` when BigQuery throws an exception |

### Integration Tests (4)

Integration tests validate cross-cutting concerns and real middleware behavior *without* mocking:

| Test | What it validates |
|---|---|
| `test_cors_headers_present` | CORS middleware injects `access-control-allow-origin` headers |
| `test_openapi_schema_generation` | OpenAPI JSON schema generates with correct title |
| `test_integration_metrics_endpoint` | Prometheus Instrumentator middleware correctly exposes `GET /metrics` |
| `test_integration_bq_auth_failure_handling` | Real BigQuery call without credentials is caught gracefully as a `500` error (not a crash) |

---

## 12-Factor App — Environment Variables

Following the [12-Factor App](https://12factor.net/) methodology, all configuration is decoupled from the codebase and injected via environment variables.

### Configuration Loading

The backend uses **Pydantic Settings** (`backend/app/config.py`) to load all config from env vars with sensible defaults for local development:

| Variable | Description | Default |
|---|---|---|
| `ENVIRONMENT` | Runtime environment (`development`, `staging`, `production`) | `development` |
| `GCP_PROJECT_ID` | Google Cloud project ID | `clima-sentinel` |
| `GCP_CREDENTIALS_JSON` | Minified JSON service account key | `None` (uses ADC locally) |
| `BQ_DATASET` | BigQuery dataset to query | `mart` |
| `BQ_LOCATION` | BigQuery dataset region | `europe-west9` |

### Environment Isolation

Each environment (staging, production) has its own set of secrets configured as **GitHub Environment Secrets**, ensuring complete isolation:

| Secret | Used In | Purpose |
|---|---|---|
| `RAILWAY_TOKEN` | Staging, Production | Railway deployment authentication |
| `RAILWAY_PROJECT_ID` | Staging, Production | Target Railway project |
| `RAILWAY_SERVICE_ID` | Staging, Production | Backend service identifier |
| `RAILWAY_FRONTEND_SERVICE_ID` | Staging, Production | Frontend service identifier |
| `GCP_SA_KEY` | MLOps pipeline | GCP service account for BigQuery access |
| `DAGSHUB_USERNAME` | MLOps pipeline | DagsHub authentication |
| `DAGSHUB_TOKEN` | MLOps pipeline | DagsHub API token |
| `MLFLOW_TRACKING_URI` | MLOps pipeline | MLflow server endpoint on DagsHub |

---

## Deployment Platform

All services are deployed to **[Railway](https://railway.app/)** using the Railway CLI (`railway up`). Each environment (staging, production) is configured as a separate Railway environment with its own service instances and environment variables.

The backend runs as a Docker container built from `backend/Dockerfile` (Python 3.11-slim, Uvicorn), exposing the port dynamically via Railway's `$PORT` variable. The frontend is a Next.js application deployed as a separate Railway service.
