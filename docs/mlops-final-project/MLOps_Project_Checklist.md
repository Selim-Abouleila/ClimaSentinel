# MLOps Final Project - Progress Tracker

Below is the detailed progress tracking table mapped directly against the official project rubric.

| Rubric Category | Specific Requirement | Status | Notes & Pending Work |
| :--- | :--- | :---: | :--- |
| **Architecture** | Python Backend (e.g., FastAPI) | ✅ **DONE** | Complete and running. |
| | NodeJS Frontend (e.g., NextJS) | ✅ **DONE** | Dashboard complete and deployed. |
| | DBMS / Database | ✅ **DONE** | Connected to Google BigQuery. |
| **Git Model** | Strict Branching (`feature/*`, `dev`, `staging`, `main`) | ✅ **DONE** | Branching model strictly followed. |
| **CI/CD Pipelines** | **PR → dev**: Run unit & integration tests | ⚠️ **IN PROGRESS** | Tests exist, need to finalize CI setup. |
| | **PR → dev**: Build Docker images (no push) | ⚠️ **IN PROGRESS** | Need to verify Docker build without push. |
| | **dev → staging**: Full test suite | ⚠️ **IN PROGRESS** | Ongoing. |
| | **dev → staging**: Deploy code to staging | ✅ **DONE** | Railway staging deployment is live! |
| | **dev → staging**: Deploy candidate model from MLFlow | 🔲 **PENDING** | Placeholder currently in CI pipeline. |
| | **staging → main**: Passing model promotion gates | 🔲 **PENDING** | Need to implement quality gates in CI. |
| | **staging → main**: Deploy code/models to prod | ✅ **DONE** | Railway prod deployment is configured. |
| **12-Factor App** | Unique env vars generated from GitHub secrets | ✅ **DONE** | GitHub Secrets fully configured for Railway. |
| **Testing** | 3 Unit Tests | ✅ **DONE** | Core health and config tests complete. |
| | 2 Integration Tests | 🔲 **PENDING** | Need to ensure exactly 2 are present. |
| | 1 End-to-End Test | 🔲 **PENDING** | Playwright test needs to be written. |
| **Data Versioning** | Track raw training data with DVC | 🔲 **PENDING** | |
| | Store data remotely (S3, GDrive, etc.) | 🔲 **PENDING** | |
| | Reference data explicitly in training runs | 🔲 **PENDING** | |
| **Model Registry** | MLflow experiments + DagsHub | 🔲 **PENDING** | |
| | Log metrics, parameters, DVC version, Git commit | 🔲 **PENDING** | |
| **Promotion Pipeline**| Train candidate model | 🔲 **PENDING** | |
| | Register version in MLflow | 🔲 **PENDING** | |
| | Deploy automatically to staging | 🔲 **PENDING** | |
| | Automated quality gates (e.g., accuracy, latency) | 🔲 **PENDING** | |
| | Promote to Production stage in registry if passed | 🔲 **PENDING** | |
| **Monitoring** | Expose metrics through `/metrics` | 🔲 **PENDING** | |
| | Configure Prometheus to scrape | 🔲 **PENDING** | |
| | Deploy Grafana & connect to Prometheus | 🔲 **PENDING** | |
| | Dashboard (Reqs, Latency, Errors, Health) | 🔲 **PENDING** | |
| **Deployment** | Application is publicly accessible | ✅ **DONE** | Both frontend and backend are live. |
| | Production serves from Production MLflow stage | 🔲 **PENDING** | |
| **Deliverables** | GitHub repository | ✅ **DONE** | |
| | Public production URL | ✅ **DONE** | |
| | README (diagram, CI/CD, promotion, reproducibility) | 🔲 **PENDING** | Need to write the final README docs. |

---

### Priority Next Steps:
1. Complete the **Playwright E2E Test**.
2. Set up **DVC** for data versioning.
3. Integrate **MLFlow / DagsHub** for model registry tracking.
4. Add **Prometheus & Grafana** for monitoring.
