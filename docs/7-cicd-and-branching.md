# 7. CI/CD and Branching Strategy

This project adheres to a strict Git branching model and automated CI/CD pipeline to ensure code quality, isolated environments, and seamless deployments.

## Branching Model

We use the following strict branching strategy to manage development:

* **`feature/*`**: All active development happens here. Developers branch off from `dev`, commit their changes, and open a Pull Request (PR) against `dev`.
* **`dev`**: The integration branch. Features are merged here to test how they interact together.
* **`staging`**: The pre-production validation branch. Used as a final testing ground (including end-to-end tests) against live data before going to production.
* **`main`**: The production branch. Only heavily tested and approved code makes it here.

## Automated CI/CD Pipelines

Our CI/CD pipelines are built using **GitHub Actions**. They automatically enforce quality gates and handle deployments to Railway.

### 1. PR to `dev`
When a feature branch opens a PR against `dev`, the pipeline automatically:
- Runs all unit tests.
- Runs all integration tests.
- Builds the Docker images to verify they compile successfully (without pushing to a registry).

### 2. Merge to `staging`
When code is merged from `dev` into `staging`, the pipeline:
- Runs the full test suite again to prevent regressions.
- Automatically deploys the codebase to the **Staging Environment** on Railway.
- *(Pending)* Deploys the candidate model from the MLFlow registry.

### 3. Merge to `main` (Production)
When `staging` is approved and merged into `main`:
- The pipeline checks that all model promotion gates have passed.
- Automatically deploys the exact code to the **Production Environment** on Railway.

## Testing Strategy
Our testing suite focuses on meaningful logic validation through Mocking external dependencies:
- **Unit Tests**: Includes edge case testing such as returning a clean `404 Not Found` when BigQuery returns empty records, and gracefully catching exceptions as `500 Internal Server Errors` rather than failing outright. Trivial tests are avoided to ensure testing robustness.

## Environment Variables
Following the 12-Factor App methodology, all secrets (like Railway tokens, GCP credentials) are completely decoupled from the codebase and injected dynamically during the GitHub Actions runs via **GitHub Secrets**.
