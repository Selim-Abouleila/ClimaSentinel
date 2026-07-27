# 7. CI/CD and Branching Strategy

The repository defines a four-tier Git workflow and automated checks for
development and staging. Railway staging deployment is active; Railway
production deployment is currently disabled. Branch-protection settings live in
GitHub rather than in this repository and must be verified separately.

---

## Branching Model

The intended four-tier branching strategy is:

```
feature/* ──PR──▸ dev ──push──▸ staging ──push──▸ main
```

| Branch | Role | Trigger |
|---|---|---|
| `feature/*` | All active development. Developers branch off `dev`, implement changes, and open a PR back into `dev`. | Manual |
| `dev` | Integration branch. Merging features here validates they work together. | PR merge |
| `staging` | Pre-production validation. Code is deployed to a live staging environment on Railway for final testing. | Push (from dev merge) |
| `main` | Production-gate branch. It trains and evaluates a challenger, but the current workflow does not deploy the application to Railway production. | Push (normally from a staging merge) |

> The workflows trigger on branch names; they do not themselves prove that
> direct pushes are blocked. Confirm required reviews and status checks in the
> GitHub branch-protection settings.

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
| **Run unit tests** | `pytest tests/ -v -m "not integration"` — runs all tests *not* marked as integration |
| **Run integration tests** | `pytest tests/ -v -m integration` — runs only tests marked `@pytest.mark.integration` |
| **Validate frontend** | `npm ci`, `npm run lint` and `npm run build` validate the typed rule-baseline client and production bundle |
| **Build Docker image** | `docker build -f backend/Dockerfile -t climasentinel-backend:test .` — verifies the image compiles but does **not** push to any registry |

> If any step fails, its check fails. Whether that blocks the merge depends on
> the repository's externally configured required-status-check rules.

---

### Pipeline 2 — Push to `staging` (`ci-staging.yml`)

**Trigger:** Push to the `staging` branch (i.e., a PR from `dev` is merged).

This pipeline re-runs the full test suite, builds the Docker image, and deploys both the backend and frontend to the **staging environment** on Railway.

| Step | Description |
|---|---|
| **Full test suite** | `pytest tests/ -v` — runs *all* tests (unit + integration) to catch regressions |
| **Build Docker image** | Builds `climasentinel-backend:staging` |
| **Train and register Heat/Rain challenger** | Calls the reusable MLOps workflow and returns the exact schema-v3 `ClimaSentinel_HeatRainForecaster` version for offline evaluation |
| **Evaluate candidate** | Runs per-horizon gates against same-vintage rule baselines. A passing challenger may receive `champion`; an ordinary quality rejection is reported without blocking the operational rule release. |
| **Deploy rule baseline** | After evaluation completes, deploys the backend and frontend with `railway up --environment staging`. Serving remains the transparent same-vintage rule policy independently of challenger acceptance. |
| **Live E2E** | Exercises Paris at every horizon, checks the rule-baseline API contract and global disclosure, and accepts either live availability state for optional sources. It does not force an unavailable-source case. |

The deployment job references the `staging` GitHub environment and reads
`RAILWAY_TOKEN`, `RAILWAY_PROJECT_ID`, `RAILWAY_SERVICE_ID` and
`RAILWAY_FRONTEND_SERVICE_ID` from it. The separate E2E job does **not**
reference that environment, so its required `STAGING_FRONTEND_URL` currently
must be available as a repository or organization secret.

---

### Pipeline 3 — Push to `main` / Production (`ci-production.yml`)

**Trigger:** Push to the `main` branch (i.e., a PR from `staging` is merged).

This pipeline trains and evaluates a new challenger on `main`. No application
release follows while the Railway production step is disabled. The operational
forecast policy remains the rule baseline unless a future release explicitly
integrates an accepted challenger into serving.

| Step | Description |
|---|---|
| **Challenger evaluation** | Trains first, then executes `python -m model.promote --allow-rejected` against the exact returned version. A candidate must satisfy provenance/support checks and beat the matching same-vintage Heat/Rain rule baselines before `champion` moves. A quality rejection leaves the alias unchanged but permits the workflow to complete. |
| **Production deploy** | The repository currently leaves Railway production deployment disabled. Re-enabling it may depend on successful evaluation execution, but must not require challenger acceptance while rules are the declared operational policy. |

> **Failure semantics:** `--allow-rejected` makes only a completed quality-gate
> rejection nonfatal. Authentication, registry access, missing candidate,
> artifact-contract, invalid metadata and unexpected execution failures still
> fail the workflow. A rejected candidate never moves the `champion` alias.

The final job references the `production` GitHub environment but only prints a
disabled-deployment notice. It does not currently read Railway deployment
secrets or publish an application release.

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

**Every successful workflow training run is traceable to:**
- A **DVC data version** (MD5 hash read from the `.dvc` metadata file)
- A **Git commit hash** (`git rev-parse HEAD`)

Both are logged as MLflow parameters alongside model metrics (`mse`, `mae`,
`r2`), the ordered target contract, feature schema v3, the three horizons and the
four-day purge gap. Publishing the DVC pointer after successful registration
prevents failed extraction, contract-validation or training runs from advancing
the versioned snapshot. Challenger evaluation remains downstream and does not
change the operational rule policy merely because a model was registered.

The final Git push is an important governance caveat: the reusable workflow has
`contents: write` and pushes the DVC pointer directly to the branch that invoked
it. Depending on branch-protection settings, that push can either fail or require
a bypass. It also places a data-version commit outside the normal pull-request
promotion path.

---

## Testing Strategy

All backend tests live in `backend/tests/` and run automatically in CI. Pytest's
`integration` marker separates broader application-contract tests from isolated
unit tests. Most of these tests still use FastAPI's in-process test client and
mocks; they are not live BigQuery, DagsHub or Railway integration tests.

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

Runtime BigQuery and deployment configuration is primarily supplied through
environment variables. This is not yet a complete 12-factor implementation:
the backend CORS policy is hard-coded to allow every origin, and several
workflow values and service identifiers remain fixed in repository files.

### Configuration Loading

The backend uses **Pydantic Settings** (`backend/app/config.py`) to load its
runtime BigQuery configuration from environment variables with sensible local
defaults. The final two MLflow variables below are consumed only by
`model/promote.py`; request-time serving does not read them.

| Variable | Description | Default |
|---|---|---|
| `ENVIRONMENT` | Runtime environment (`development`, `staging`, `production`) | `development` |
| `GCP_PROJECT_ID` | Google Cloud project ID | `clima-sentinel` |
| `GCP_CREDENTIALS_JSON` | Optional legacy service-account JSON supplied through the runtime secret store; avoid it where ADC or federation is available | `None` (uses ADC locally) |
| `BQ_DATASET` | BigQuery dataset to query | `mart` |
| `BQ_STAGING_DATASET` | BigQuery dataset containing dbt seeds such as `city_monthly_normals` | `stg` |
| `BQ_LOCATION` | BigQuery dataset region | `europe-west9` |
| `MLFLOW_MODEL_ALIAS` | Alias updated only by a challenger that passes every gate | `champion` |
| `MLFLOW_MODEL_VERSION` | Exact candidate version evaluated by the promotion command | unset |

### Current secret scope and isolation limitations

Secret scope follows the job that consumes it:

| Secret | Current consumer | Required scope with the present workflows |
|---|---|---|
| `RAILWAY_TOKEN`, `RAILWAY_PROJECT_ID`, `RAILWAY_SERVICE_ID`, `RAILWAY_FRONTEND_SERVICE_ID` | `deploy-staging` | `staging` GitHub environment |
| `STAGING_FRONTEND_URL` | `e2e-test` | Repository or organization, because that job has no `environment` |
| `GCP_SA_KEY`, `DAGSHUB_USERNAME`, `DAGSHUB_TOKEN`, `MLFLOW_TRACKING_URI` | Reusable training workflow | Repository or organization, because the caller jobs have no environment |
| `DAGSHUB_USERNAME`, `DAGSHUB_USER_TOKEN` or `DAGSHUB_TOKEN` | Staging promotion | `staging` GitHub environment |
| `DAGSHUB_USERNAME`, `DAGSHUB_USER_TOKEN` or `DAGSHUB_TOKEN` | Production evaluation | Repository or organization, because that job has no environment |

This is **not complete staging/production secret isolation**. In addition,
`GCP_SA_KEY` is a long-lived service-account JSON key. A production hardening
pass should use short-lived workload-identity federation and give each
environment explicitly scoped registry credentials.

### Model-registry governance limitation

Staging and production evaluation both call `model.promote` with
`MLFLOW_MODEL_ALIAS=champion`. A passing staging evaluation can therefore move
the same `champion` alias and transition the model version to MLflow's
`Production` stage before the `main` workflow runs. The operational API remains
rule-based, so this does not alter request-time forecasts, but the registry does
not currently provide an environment-separated production gate.

---

## Deployment Platform

The backend and frontend are deployed to Railway staging with the Railway CLI
(`railway up`). The repository contains a production environment gate, but its
Railway deployment step is currently disabled.

The backend runs as a Docker container built from `backend/Dockerfile` (Python 3.11-slim, Uvicorn), exposing the port dynamically via Railway's `$PORT` variable. The frontend is a Next.js application deployed as a separate Railway service.
