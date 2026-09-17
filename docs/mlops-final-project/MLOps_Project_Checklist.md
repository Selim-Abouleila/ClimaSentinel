# MLOps Final Project — Current Status

Status reviewed against the repository state proposed on **2026-08-13**. Statuses
describe code and configuration visible in Git; they do not certify the current
contents of external systems such as Railway, BigQuery, DagsHub or GitHub
branch-protection settings.

The four interpretation blockers summarized in
[Critical System Limitations](../0-critical-limitations.md) are listed as
unimplemented controls below. A green build or reachable dashboard does not
override them.

Legend: ✅ implemented · ⚠️ implemented with a material limitation · ⬜ not
implemented

| Rubric category | Requirement | Status | Current evidence and limitation |
|---|---|:---:|---|
| **Architecture** | FastAPI backend | ✅ | Backend exposes operational data, forecast, health, OpenAPI and Prometheus routes. |
| | Next.js frontend | ✅ | Next.js 16 includes overview, city detail and beta forecast routes; the staging workflow is configured to deploy it to Railway. |
| | Database | ✅ | Ingestion, dbt and API code target BigQuery raw, staging and mart layers; live dataset state is external to this review. |
| **Git model** | `feature/*` → `dev` → `staging` → `main` | ⚠️ | Workflows target these branches, but branch-protection rules are external to the repository. The MLOps workflow can also push a DVC pointer directly to its invoking branch. |
| **PR CI** | Tests for PRs to `dev` | ⚠️ | City/normals/monitoring/provenance contracts, generator behavior, ingestion failure propagation, backend unit/marker-labelled integration tests and a credential-free `dbt parse` run in separate jobs. Most “integration” tests use mocks or an in-process client; CI does not exercise live source fetchers, BigQuery loader writes or authenticated dbt run/test. |
| | Frontend lint/unit/build | ✅ | `npm ci`, lint, the Playwright-powered pure availability and backend-health proxy unit suite, and production build run for PRs to `dev`. |
| | Backend and ingestion Docker builds without push | ✅ | Both release images are built after the test job; neither is pushed by PR CI. |
| **Staging CI/CD** | Full backend tests and Docker build | ✅ | Both run on pushes to `staging`. |
| | Train and register challenger | ✅ | Reusable workflow is implemented to extract a BigQuery snapshot, train six Heat/Rain outputs and register an exact MLflow version. A successful current run/version is not pinned in this repository. |
| | Evaluate promotion gates | ⚠️ | Quality/provenance gates are implemented, but staging and production share the same `champion` alias; a passing staging run can move MLflow's Production state. |
| | Deploy application | ✅ | With pinned Railway CLI and detached uploads, staging queues the compatibility frontend, overlaps its build with the read-only v2 readiness gate, exact-marker-verifies it, then queues the v2 backend. A no-cache frontend proxy must report the exact healthy backend release ID before E2E; the two service cutovers are not parallel. |
| | Live E2E | ⚠️ | Exact frontend/backend commit-run identity is gated before Playwright, which covers Paris Day +1/+2/+3, freezes the original 10-city forecast selector and verifies Stockholm's unmonitored River state. It does not render/assert the complete 20-city overview, all forecast cities, injected failure states or backend dependency readiness. |
| **Production CI/CD** | Evaluate challenger on `main` | ✅ | The workflow trains and evaluates an exact version; completed quality rejection is nonfatal while contract/operational failures remain fatal. |
| | Deploy application to Railway production | ⬜ | The production deployment step is explicitly disabled and only prints a notice. |
| **Configuration and secrets** | Environment-based runtime config | ⚠️ | BigQuery/Railway settings use environment variables, but CORS and several workflow values remain hard-coded. |
| | Isolated staging/production secrets | ⚠️ | Only jobs that declare a GitHub environment can read its environment secrets. Training, production evaluation and staging E2E currently require some repository/organization secrets instead. |
| | Keyless cloud authentication | ⬜ | MLOps currently uses a long-lived `GCP_SA_KEY` JSON secret rather than workload-identity federation. |
| **Testing** | Backend unit and contract tests | ✅ | Formula, v2 availability/coverage/aggregate schema, training, promotion and serving-policy branches have automated tests. |
| | Frontend availability unit tests | ✅ | Pure tests cover legacy compatibility, explicit v2 availability, partial/all-unavailable aggregation, measured zero, missing/unmonitored factors and the 36-hour stale threshold. |
| | dbt operational contracts | ⚠️ | Singular tests cover v2 spine, monitoring, exact-run coherence, raw consistency, availability and deterministic worst-day behavior; PR CI parses only, while `make deploy` runs the warehouse tests. |
| | Live external integration tests | ⚠️ | When executed, the staging forecast smoke test reaches the Railway frontend/API and indirectly BigQuery. Backend tests do not exercise live BigQuery/DagsHub/MLflow, and no current successful run is pinned here. |
| | End-to-end test | ⚠️ | One forecast smoke scenario exists with the scope limits described above. |
| **Scientific interpretation** | Calibrated risk probability or severity index | ⬜ | The operational Tipping Score is a deterministic maximum of hand-set component formulas. No calibration, sensitivity study or outcome mapping supports probability, severity or response claims. |
| | Completed-run serving gate | ⬜ | The active selector accepts the newest run with any raw evidence. Freshness and partial-coverage UI warnings do not prove that every expected source completed. |
| | Trustworthy UTC valid time | ⬜ | Provider-local offset-free clock values are stored in the legacy `valid_ts_utc` field. Exact UTC instants, DST audit and hour-level lead times are not supported. |
| | Verified archive model provenance | ⬜ | Archive requests neither pin nor retain a source model/version. `era5_*` and `open_meteo_era5` are legacy identifiers, not verified ERA5 evidence. |
| **Data versioning** | Track and store training snapshot with DVC | ⚠️ | Successful training runs `dvc add` and `dvc push`, but the pointer on the current `dev` line references a legacy snapshot incompatible with schema v3. Workflow-generated pointer commits are branch-local, so `staging` and `dev` can diverge. |
| | Link data and code to training run | ⚠️ | MLflow logs the checked-out source commit and fresh DVC object hash. The workflow commits the updated pointer afterwards under a different Git ID, so neither Git ID nor hash is a complete provenance reference by itself. |
| | Publish pointer through reviewed branch flow | ⚠️ | The workflow commits and pushes the pointer directly after registration. |
| **Model registry** | MLflow experiments and DagsHub registry | ⚠️ | Registration code and tests exist, but no current registry export, run ID, model version or alias target is pinned in Git; external state cannot be verified from the repository alone. |
| | Environment-separated promotion | ⬜ | Staging and production do not have separate aliases/stages/credentials. |
| | Exact manual candidate selection | ⚠️ | CI passes `MLFLOW_MODEL_VERSION`; the local promotion command falls back to the numerically latest registry version when it is omitted, which is ambiguous under concurrent registration. |
| **Serving policy** | Serve promoted ML model | ⬜ | The deployed API intentionally serves deterministic same-vintage rules for all five components; registered models remain offline challengers. |
| | Honest beta/validation disclosure | ⚠️ | The forecast has a prominent beta badge and global validation note. Detailed per-factor provenance exists in the API but is not visibly rendered on each card. |
| **API operations** | Hardened public API | ⬜ | There is no application auth, rate limiting or response cache; only current-score list reads are bounded (`1..100`), while other list routes remain unbounded. CORS is permissive and docs/metrics are public. |
| | Dependency readiness | ⚠️ | `/health` remains process liveness only. Staging has a one-time v2 schema/20-city/run gate with a 36-hour age ceiling, but it provides neither continuous BigQuery readiness nor a durable completed-run manifest. |
| | History endpoint | ✅ | `/data/history-scores` orders by the mart's `date` column and validates nullable factor/status/coverage rows with a typed response model. Its list limit is not yet bounded. |
| **Monitoring** | Expose Prometheus metrics | ✅ | FastAPI exposes generic HTTP/process metrics at public `/metrics`. |
| | Prometheus/Grafana dashboard | ⚠️ | A local Docker Compose demo scrapes the configured Railway backend and provisions four panels. It is not deployed monitoring. |
| | Operational snapshot visibility | ⚠️ | V2 exposes the selected run ID/timestamp; overview/detail warn after 36 hours and flag partial factor coverage. No durable completed-run manifest or freshness alert exists, so failed/overlapping runs remain a hardening gap. |
| | Persistence, alerting and secure access | ⬜ | No data volumes, alert rules/contact points or production credentials/access controls are configured. |
| **Deliverables** | Root and component documentation | ✅ | Architecture, 20-city operational/10-city forecast scope, pipeline, API, frontend, testing and limitation documents are present. |
| | Public application | ⚠️ | The README links a public Railway dashboard, but availability and the deployed revision are external state; the repository's production deployment workflow is disabled. |

## Priority next steps

1. Either calibrate and validate the operational score and bands against stated
   outcomes, or rename and present them consistently as prototype heuristics.
2. Add a durable completed-run manifest and require it in serving, release
   readiness and monitoring before calling a snapshot complete.
3. Migrate provider-local timestamps to offset-aware UTC instants while
   preserving a separate local calendar field, then rebuild time-dependent
   marts and validation data.
4. Pin and persist the Open-Meteo Archive source model/version; until then,
   remove ERA5 provenance claims from scientific interpretation and treat the
   existing machine-readable names as legacy only.
5. Publish a schema-v3 DVC pointer on `dev` and a pinned evaluation record with
   the source commit, pointer commit, DVC hash, MLflow run/version and held-out
   support.
6. Bound the remaining history/zone list inputs and add a typed zone response.
7. Harden the API with explicit CORS origins, rate/cost controls, safer errors
   and a dependency-readiness check.
8. Separate staging and production registry aliases/credentials and remove
   direct protected-branch data-pointer pushes.
9. Replace long-lived GCP keys with workload-identity federation.
10. Expand E2E coverage beyond the current Paris/Stockholm paths.
11. Treat monitoring as production only after credentials, persistence, alerting
   and deployment are implemented.
