# MLOps Final Project: Progress Report

This document tracks our progress against the MLOps Final Project requirements.

## ✅ Completed Requirements

### 1. Git Branching Model
- **Status:** Done
- **Implementation:** We established the strict branching strategy required:
  - `feature/*` for active development.
  - `dev` for integration.
  - `staging` for pre-production validation.
  - `main` for production.

### 2. CI/CD Pipelines
- **Status:** Done (with placeholders for MLflow)
- **Implementation:** We created three GitHub Actions workflows (`.github/workflows/`):
  - **PR → dev** (`ci-dev.yml`): Runs unit tests, integration tests, and builds Docker images without pushing.
  - **dev → staging** (`ci-staging.yml`): Runs the full test suite, builds the Docker image, and uses the Railway CLI to deploy to the staging environment (requires `RAILWAY_TOKEN`). A placeholder is added for deploying the candidate model from MLflow.
  - **staging → main** (`ci-production.yml`): Includes placeholders for model promotion gates. If they pass, it uses the Railway CLI to deploy to production.

### 3. Cloud Deployment
- **Status:** Done
- **Implementation:** The application is configured to deploy to **Railway**. 
- *Important Note:* We explicitly use the Railway CLI in GitHub Actions rather than Railway's built-in "auto-deploy". This ensures that deployments only happen *after* our quality gates pass, satisfying the requirement that "if a gate fails, production must not change".

### 4. Testing Requirements (Partial)
- **Status:** Partially Done
- **Implementation:** 
  - **3 Unit Tests** implemented (`tests/test_health.py` - testing `/` and `/health` endpoints).
  - **2 Integration Tests** implemented (`tests/test_health.py` - testing CORS headers and OpenAPI schema).
  - *Pending:* 1 End-to-End test (will be added once the frontend is built).

### 5. Web App Backend
- **Status:** Partially Done
- **Implementation:** A bare-minimum Python FastAPI backend is implemented, containerized using Docker, and ready to serve the ML model.

---

## ⏳ Pending Requirements

The following tasks are next on the roadmap to complete the project:

1. **Data Versioning (DVC):** Track raw training data, store remotely, and reference data versions explicitly in training runs.
2. **Model Versioning & Registry (MLflow + DagsHub):** Log metrics, parameters, data/code versions, and register models.
3. **Model Promotion Pipeline:** Train candidate models, deploy automatically to staging, and implement the automated quality gates (e.g., accuracy threshold) in GitHub Actions.
4. **Monitoring (Prometheus & Grafana):** Expose `/metrics` on the backend, configure Prometheus scraping, and create a Grafana dashboard for live production monitoring.
5. **Frontend Application:** Build a NodeJS framework frontend (ReactJS/NextJS) and write the remaining 1 End-to-End test.
6. **12-Factor App:** Ensure all environments have unique environment variables generated from GitHub secrets.
