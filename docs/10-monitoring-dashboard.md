# 10. Local Monitoring Demo (Prometheus and Grafana)

The repository includes a local Docker Compose demonstration that scrapes the
public FastAPI `/metrics` endpoint and visualizes the resulting Prometheus
series in Grafana. It is **not a deployed production monitoring service**.

## Current architecture

```text
Local Prometheus --scrapes every 15 s--> Railway backend /metrics
Local Grafana    --queries-------------> Local Prometheus
```

The checked-in Prometheus configuration targets
`climasentinel-production.up.railway.app` over HTTPS. Change
`monitoring/prometheus/prometheus.yml` if the backend hostname changes or if a
different environment should be observed. The hostname and the provisioned
dashboard title contain “production,” but that label does not make this local
Compose stack a production deployment. The current `main` workflow does not
deploy Railway production, and Compose neither provisions nor verifies this
remote target; confirm its ownership, release and availability separately in
Prometheus's target-status page.

The backend uses `prometheus-fastapi-instrumentator`, which exposes generic HTTP
and Python-process metrics. These series cover all instrumented routes; they are
not model-specific prediction-quality, drift or business-outcome metrics.

The 20-city expansion does not add data-plane observability to this stack.
Neither Prometheus nor the provisioned Grafana dashboard verifies that either
scheduled Cloud Run execution at 06:00 or 18:00 UTC processed all 20 cities,
that the nominal ~5,935 raw rows per run (~11,870 across the two scheduled runs
per UTC day) arrived, that all 240 monthly-normal rows were seeded, or that
`mart_city_score_current_v2` contains 20 fresh city rows. Those checks require
Cloud Run execution monitoring plus explicit BigQuery/dbt freshness and
completeness signals; backend HTTP traffic alone cannot establish them.

## Operational snapshot visibility

The active v2 current, history and detail API payloads expose
`operational_ingestion_run_id` and `operational_ingested_at_utc`. The Next.js
overview and city-detail pages display that selected snapshot timestamp and
mark it stale after 36 hours. Scored city cards explicitly flag partial factor
coverage (for example, one available factor out of four monitored), and the
network-mean card reports how many included scored cities have partial signal
coverage. Unscored cities are excluded from the mean and reported separately.

These are product-level transparency controls, not Prometheus monitoring or an
ingestion transaction guarantee. The pipeline does not yet persist a completed
run manifest. A totally failed run can leave the older snapshot selected, and
an overlapping/in-progress run can briefly be the most recent run visible to
the exact-run selector. The 36-hour banner makes prolonged staleness visible,
but a durable run-state/audit table plus freshness alerts remain future
hardening.

The staging deployment readiness gate checks required v2 columns, exact
checked-in 20-city seed/current/detail membership, one coherent run ID and a
snapshot age of at most 36 hours before cutting the backend over. It is a
one-time release gate over relations already created by `make deploy`; it does
not run dbt, monitor later scheduled executions, or replace the missing run
manifest.

## What the provisioned panels actually show

| Panel | Current query | Semantics |
|---|---|---|
| Total Request Volume | `sum(http_requests_total)` | A cumulative counter across all instrumented HTTP routes, not a request rate and not forecast-only traffic |
| Prediction Request Latency (p95) | `histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le))` | An aggregate p95 over all included handlers/statuses; the current query does not isolate the forecast endpoint |
| Failed Requests (Error Rate) | `sum(http_requests_total{status=~"5.."})` | A cumulative count of 5xx responses, not a rate and not 4xx + 5xx |
| Backend Uptime / Health | `time() - process_start_time_seconds` | Backend process age in seconds; it is not dependency readiness or Prometheus target health |

The panel titles “Prediction Request Latency,” “Error Rate” and “Health” are
therefore legacy labels and are broader or stronger than their actual queries.
Grafana refreshes every 5 seconds while Prometheus scrapes every 15 seconds, so
several dashboard refreshes can legitimately show the same sample.

Prometheus's own `up{job="climasentinel-backend"}` series indicates whether the
scrape target is reachable. The provisioned dashboard does not currently use
that series. The backend `/health` route reports process liveness and release
identity, but it does not test BigQuery; staging CD uses `release_id` only to
identify the routed build.

## Important limitations

- Prometheus and Grafana run on the developer's Docker host. Their published
  ports are not restricted to loopback in the Compose file and may be reachable
  through other host interfaces, depending on Docker and firewall settings.
- No Prometheus alert rules, Grafana alert rules, notification contact points or
  paging integrations are provisioned.
- Neither service has a persistent data volume. Prometheus history and Grafana
  runtime changes can be lost when containers are removed or recreated.
- The Compose file uses floating `latest` image tags.
- Grafana allows anonymous Viewer access and uses the default
  `admin` / `admin` administrator credentials.
- Prometheus is exposed on local port `9090` and Grafana on `3000`; the latter
  conflicts with the frontend's default development port.
- The backend `/metrics` endpoint is public and unauthenticated.
- There are no per-city ingestion-success, source-freshness, mart-row-count or
  operational-versus-forecast-scope metrics for the 20/10 city contracts.
- The 36-hour frontend warning has no corresponding Prometheus alert or paging
  path.

These defaults are acceptable only for a local demonstration on a trusted
machine. Do not expose this Compose stack to a shared or public network without
pinning images, changing credentials, disabling anonymous access, restricting
network access, adding persistence and configuring alerts.

## Run locally

Prerequisite: Docker Desktop or another Docker Compose-compatible runtime.

```powershell
cd monitoring
docker compose up -d
```

Open:

- Grafana: `http://localhost:3000`
- Prometheus: `http://localhost:9090`
- Prometheus target status: `http://localhost:9090/targets`

If the frontend is already using port `3000`, stop it or change the Grafana port
mapping before starting the stack.

Any backend HTTP traffic can increment the request counter. To generate a small
sample, open the configured backend, `/docs`, or a data endpoint several times,
then select a recent time range in Grafana. `No data` can mean the target is
down, the hostname is stale, the metric name/query does not match the exposed
series, or no samples have been scraped yet; it does not necessarily mean there
were no forecast requests.

## Stop the demo

```powershell
docker compose down
```

To also remove the downloaded images:

```powershell
docker compose down --rmi all
```
