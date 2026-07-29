# MLOps Final Project — Current Status

Status reviewed against the `dev`-line repository on **2026-07-28**. Statuses
describe code and configuration visible in Git; they do not certify the current
contents of external systems such as Railway, BigQuery, DagsHub or GitHub
branch-protection settings.

Legend: ✅ implemented · ⚠️ implemented with a material limitation · ⬜ not
implemented

| Rubric category | Requirement | Status | Current evidence and limitation |
|---|---|:---:|---|
| **Architecture** | FastAPI backend | ✅ | Backend exposes operational data, forecast, health, OpenAPI and Prometheus routes. |
| | Next.js frontend | ✅ | Next.js 16 includes overview, city detail and beta forecast routes; the staging workflow is configured to deploy it to Railway. |
| | Database | ✅ | Ingestion, dbt and API code target BigQuery raw, staging and mart layers; live dataset state is external to this review. |
| **Git model** | `feature/*` → `dev` → `staging` → `main` | ⚠️ | Workflows target these branches, but branch-protection rules are external to the repository. The MLOps workflow can also push a DVC pointer directly to its invoking branch. |
| **PR CI** | Tests for PRs to `dev` | ⚠️ | Unit/contract and marker-labelled integration tests run in separate commands. Most “integration” tests use mocks or an in-process client; CI does not exercise source fetchers, BigQuery loader writes or dbt compile/run/test. |
| | Frontend lint/build | ✅ | `npm ci`, lint and production build run for PRs to `dev`. |
| | Backend Docker build without push | ✅ | The backend image is built after backend tests. |
| **Staging CI/CD** | Full backend tests and Docker build | ✅ | Both run on pushes to `staging`. |
| | Train and register challenger | ✅ | Reusable workflow is implemented to extract a BigQuery snapshot, train six Heat/Rain outputs and register an exact MLflow version. A successful current run/version is not pinned in this repository. |
| | Evaluate promotion gates | ⚠️ | Quality/provenance gates are implemented, but staging and production share the same `champion` alias; a passing staging run can move MLflow's Production state. |
| | Deploy application | ✅ | The workflow is configured to deploy backend and frontend to Railway staging with the operational all-rule policy. |
| | Live E2E | ⚠️ | Playwright covers Paris and Day +1/+2/+3 in desktop Chromium. It does not pin the backend commit or cover all cities/pages/failure states. |
| **Production CI/CD** | Evaluate challenger on `main` | ✅ | The workflow trains and evaluates an exact version; completed quality rejection is nonfatal while contract/operational failures remain fatal. |
| | Deploy application to Railway production | ⬜ | The production deployment step is explicitly disabled and only prints a notice. |
| **Configuration and secrets** | Environment-based runtime config | ⚠️ | BigQuery/Railway settings use environment variables, but CORS and several workflow values remain hard-coded. |
| | Isolated staging/production secrets | ⚠️ | Only jobs that declare a GitHub environment can read its environment secrets. Training, production evaluation and staging E2E currently require some repository/organization secrets instead. |
| | Keyless cloud authentication | ⬜ | MLOps currently uses a long-lived `GCP_SA_KEY` JSON secret rather than workload-identity federation. |
| **Testing** | Backend unit and contract tests | ✅ | Formula, schema, training, promotion and serving-policy branches have automated tests. |
| | Live external integration tests | ⚠️ | When executed, the staging forecast smoke test reaches the Railway frontend/API and indirectly BigQuery. Backend tests do not exercise live BigQuery/DagsHub/MLflow, and no current successful run is pinned here. |
| | End-to-end test | ⚠️ | One forecast smoke scenario exists with the scope limits described above. |
| **Data versioning** | Track and store training snapshot with DVC | ⚠️ | Successful training runs `dvc add` and `dvc push`, but the pointer on the current `dev` line references a legacy snapshot incompatible with schema v3. Workflow-generated pointer commits are branch-local, so `staging` and `dev` can diverge. |
| | Link data and code to training run | ⚠️ | MLflow logs the checked-out source commit and fresh DVC object hash. The workflow commits the updated pointer afterwards under a different Git ID, so neither Git ID nor hash is a complete provenance reference by itself. |
| | Publish pointer through reviewed branch flow | ⚠️ | The workflow commits and pushes the pointer directly after registration. |
| **Model registry** | MLflow experiments and DagsHub registry | ⚠️ | Registration code and tests exist, but no current registry export, run ID, model version or alias target is pinned in Git; external state cannot be verified from the repository alone. |
| | Environment-separated promotion | ⬜ | Staging and production do not have separate aliases/stages/credentials. |
| | Exact manual candidate selection | ⚠️ | CI passes `MLFLOW_MODEL_VERSION`; the local promotion command falls back to the numerically latest registry version when it is omitted, which is ambiguous under concurrent registration. |
| **Serving policy** | Serve promoted ML model | ⬜ | The deployed API intentionally serves deterministic same-vintage rules for all five components; registered models remain offline challengers. |
| | Honest beta/validation disclosure | ⚠️ | The forecast has a prominent beta badge and global validation note. Detailed per-factor provenance exists in the API but is not visibly rendered on each card. |
| **API operations** | Hardened public API | ⬜ | There is no application auth, rate limiting or bounded list pagination; CORS is permissive and docs/metrics are public. |
| | Dependency readiness | ⬜ | `/health` is process liveness only and does not test BigQuery. |
| | History endpoint | ⚠️ | `/data/history-scores` exists, but it orders by `prediction_date` while the mart column is `date`; the route currently returns `500`. |
| **Monitoring** | Expose Prometheus metrics | ✅ | FastAPI exposes generic HTTP/process metrics at public `/metrics`. |
| | Prometheus/Grafana dashboard | ⚠️ | A local Docker Compose demo scrapes the configured Railway backend and provisions four panels. It is not deployed monitoring. |
| | Persistence, alerting and secure access | ⬜ | No data volumes, alert rules/contact points or production credentials/access controls are configured. |
| **Deliverables** | Root and component documentation | ✅ | Architecture, pipeline, API, frontend, testing and limitation documents are present. |
| | Public application | ⚠️ | The README links a public Railway dashboard, but availability and the deployed revision are external state; the repository's production deployment workflow is disabled. |

## Priority next steps

1. Publish a schema-v3 DVC pointer on `dev` and a pinned evaluation record with
   the source commit, pointer commit, DVC hash, MLflow run/version and held-out
   support.
2. Fix `/data/history-scores` and add bounded, typed operational responses.
3. Harden the API with explicit CORS origins, rate/cost controls, safer errors
   and a dependency-readiness check.
4. Separate staging and production registry aliases/credentials and remove
   direct protected-branch data-pointer pushes.
5. Replace long-lived GCP keys with workload-identity federation.
6. Expand E2E coverage and add an exact backend release marker.
7. Treat monitoring as production only after credentials, persistence, alerting
   and deployment are implemented.
