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
| **Validate frontend** | `npm ci`, `npm run lint` and `npm run build` validate the typed rule-baseline client and production bundle |
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
| **Train and register Heat/Rain challenger** | Calls the reusable MLOps workflow and returns the exact schema-v3 `ClimaSentinel_HeatRainForecaster` version for offline evaluation |
| **Evaluate candidate** | Runs per-horizon gates against same-vintage rule baselines. A passing challenger may receive `champion`; an ordinary quality rejection is reported without blocking the operational rule release. |
| **Deploy rule baseline** | Deploys the backend and frontend using transparent same-vintage rules for all five components, independently of challenger acceptance. |
| **Live E2E** | Confirms that every horizon returns the rule-baseline contract, null model intervals, honest validation labels and nullable optional-source behavior. |

**Railway secrets used:** `RAILWAY_TOKEN`, `RAILWAY_PROJECT_ID`, `RAILWAY_SERVICE_ID`, `RAILWAY_FRONTEND_SERVICE_ID` — all injected from the `staging` GitHub environment.

---

### Pipeline 3 — Push to `main` / Production (`ci-production.yml`)

**Trigger:** Push to the `main` branch (i.e., a PR from `staging` is merged).

This pipeline evaluates a new challenger before the production release. The
operational forecast policy remains the rule baseline unless a future release
explicitly integrates an accepted challenger into serving.

| Step | Description |
|---|---|
| **Challenger evaluation** | Trains first, then executes `python -m model.promote --allow-rejected` against the exact returned version. A candidate must satisfy provenance/support checks and beat the matching same-vintage Heat/Rain rule baselines before `champion` moves. A quality rejection leaves the alias unchanged but permits the rule-baseline release to continue. |
| **Production deploy** | The repository currently leaves Railway production deployment disabled. Re-enabling it may depend on successful evaluation execution, but must not require challenger acceptance while rules are the declared operational policy. |

> **Failure semantics:** `--allow-rejected` makes only a completed quality-gate
> rejection nonfatal. Authentication, registry access, missing candidate,
> artifact-contract, invalid metadata and unexpected execution failures still
> fail the workflow. A rejected candidate never moves the `champion` alias.

**Railway secrets used:** Same structure as staging, scoped to the `production` GitHub environment.

---

### Pipeline 4 — MLOps Training Pipeline (`ci-mlops.yml`)

**Trigger:** Reusable calls from staging/production deployment workflows, or manual dispatch (`workflow_dispatch`).

This pipeline handles the full ML lifecycle: data extraction, versioning, training, and model registration.

| Step | Description |
|---|---|
| **Checkout code** | With `contents: write` permission for auto-committing DVC files |
| **Set up Python 3.11** | Installs the repository's backend requirements plus DVC so training, serving validation and CI use one dependency contract. |
| **Authenticate with GCP** | Uses `google-github-actions/auth@v2` with `GCP_SA_KEY` secret |
| **Configure DVC remote** | Sets up DagsHub DVC remote with basic auth (`DAGSHUB_USERNAME`, `DAGSHUB_TOKEN`) |
| **Extract data from BigQuery** | Runs `python -m model.extract_data` against `mart_ml_training_examples` |
| **Stage DVC metadata** | Runs `dvc add model/data/training_snapshot.csv` locally so the candidate logs the exact snapshot hash |
| **Validate MLflow secrets** | Checks that `MLFLOW_TRACKING_URI` is set before training |
| **Train & register challenger** | Trains six independent outputs (realized Heat and Rain × Day +1/+2/+3), validates schema v3, registers one atomic `ClimaSentinel_HeatRainForecaster` challenger, and returns its exact concrete version |
| **Publish successful data version** | Only after training and registration succeed, runs `dvc push`, commits the updated `.dvc` pointer with `[skip ci]`, and pushes it to Git |

**Every training run is traceable to:**
- A **DVC data version** (MD5 hash read from the `.dvc` metadata file)
- A **Git commit hash** (`git rev-parse HEAD`)

Both are logged as MLflow parameters alongside model metrics (`mse`, `mae`,
`r2`), the ordered target contract, feature schema v3, the three horizons and the
four-day purge gap. Publishing the DVC pointer after successful registration
prevents failed extraction, contract-validation or training runs from advancing
the versioned snapshot. Challenger evaluation remains downstream and does not
change the operational rule policy merely because a model was registered.

---

## Testing Strategy

All backend tests live in `backend/tests/` and run automatically in CI. Pytest's
`integration` marker separates tests that exercise multiple real components
from isolated unit/contract tests.

| Test module | Main contract covered |
|---|---|
| `test_health.py` | Health, operational endpoints, middleware and OpenAPI generation |
| `test_forecast_rules.py` | All five rule formulas, clipping, source coverage, target-month Heat normal and Day +3 use of same-vintage Day +4 context |
| `test_model_extraction.py` | Direct training-mart extraction, exact schema/provenance and absence of leaky filling |
| `test_ml_pipeline.py` | Schema-v3 challenger preprocessing, six-output order, horizon slicing, four-day purge and endpoint rule semantics |
| `test_model_training.py` | Heat/Rain challenger metrics, identical-row rule baselines, MLflow/DVC provenance and registered artifact contract |
| `test_model_promotion.py` | Baseline-relative gates, horizon-specific ceilings, exact registry-artifact validation, evidence/contract failures and explicit nonfatal quality rejection |
| `test_model_serving_integration.py` | Registry-independent rule policy, null model provenance/intervals and all three horizons |

The staging Playwright suite adds a live deployment check after challenger
evaluation and Railway deployment. It verifies the rule-baseline API rather
than assuming that the newly registered candidate passed. See
[End-to-End Testing](13-end-to-end-testing.md).

---

## 12-Factor App — Environment Variables

Following the [12-Factor App](https://12factor.net/) methodology, all configuration is decoupled from the codebase and injected via environment variables.

### Configuration Loading

The backend uses **Pydantic Settings** (`backend/app/config.py`) to load its
runtime BigQuery configuration from environment variables with sensible local
defaults. The final two MLflow variables below are consumed only by
`model/promote.py`; request-time serving does not read them.

| Variable | Description | Default |
|---|---|---|
| `ENVIRONMENT` | Runtime environment (`development`, `staging`, `production`) | `development` |
| `GCP_PROJECT_ID` | Google Cloud project ID | `clima-sentinel` |
| `GCP_CREDENTIALS_JSON` | Minified JSON service account key | `None` (uses ADC locally) |
| `BQ_DATASET` | BigQuery dataset to query | `mart` |
| `BQ_STAGING_DATASET` | BigQuery dataset containing dbt seeds such as `city_monthly_normals` | `stg` |
| `BQ_LOCATION` | BigQuery dataset region | `europe-west9` |
| `MLFLOW_MODEL_ALIAS` | Alias updated only by a challenger that passes every gate | `champion` |
| `MLFLOW_MODEL_VERSION` | Exact candidate version evaluated by the promotion command | unset |

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
