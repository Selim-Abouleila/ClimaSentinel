# 2. Ingestion Pipeline

The ClimaSentinel ingestion pipeline is a serverless, automated data pipeline
running on Google Cloud Platform. It scales to zero when idle and actively
fetches weather forecasts, air-quality forecasts, river-discharge forecasts and
lagged historical reanalysis for a configurable set of cities. Support code for
long-term CMIP6 projections remains in the repository, but that fetch is
disabled in scheduled ingestion.

> **Read before relying on pipeline output:** [Critical limitations](0-critical-limitations.md)
> records unresolved correctness boundaries. In particular, a partial,
> failed or still-running ingestion with any raw evidence can become the
> active operational snapshot, and hourly `valid_ts_utc` values are currently
> provider-local clock text interpreted as UTC. The current implementation has
> not fixed either issue.

## Architecture

The ingestion process relies on three core Google Cloud services:

1. **Cloud Scheduler**: Fires an HTTP request to the Cloud Run job every 12
   hours, at `06:00` and `18:00 UTC` (`0 6,18 * * *`).
2. **Cloud Run Job**: Executes the Python runner that pulls the APIs and invokes
   dbt, with a 1,200-second task timeout for the sequential 20-city workload.
   This is an operational budget, not a guarantee that every worst-case source
   timeout can complete before the task deadline.
3. **BigQuery**: Stores appended raw rows in time-partitioned tables and hosts
   the dbt relations.

Terraform manages the Cloud Run Job, Scheduler, service accounts and their IAM
bindings. The `raw` dataset is a manual prerequisite and the Python loader
creates active source tables on first use. The bootstrap script, rather than
Terraform, creates the Artifact Registry repository; Cloud Build builds and
pushes its image.

## Configuration: The City List

The ingestion script iterates over 20 major European cities configured in
`config/cities.csv`. To add or remove cities, update the CSV, then rebuild and
redeploy the ingestion image; pushing the file alone does not update the running
Cloud Run Job. The `river_enabled` column controls whether flood/river discharge
data is fetched for that city. `make validate-cities` requires every active city
to have exactly 12 monthly-normal rows and one matching
`city_signal_monitoring` row, enforces River alignment with `river_enabled`,
and keeps the separate forecast-city contract frozen to its original 10 IDs.

| City | Country | Latitude | Longitude | River Monitoring |
|---|---|---|---|---|
| Paris | FR | 48.853 | 2.348 | ✅ |
| London | GB | 51.508 | -0.125 | — |
| Madrid | ES | 40.416 | -3.702 | — |
| Berlin | DE | 52.524 | 13.410 | — |
| Rome | IT | 41.891 | 12.511 | — |
| Amsterdam | NL | 52.374 | 4.889 | ✅ |
| Athens | GR | 37.983 | 23.727 | — |
| Warsaw | PL | 52.229 | 21.011 | ✅ |
| Lisbon | PT | 38.716 | -9.133 | — |
| Stockholm | SE | 59.329 | 18.068 | — |
| Vienna | AT | 48.208 | 16.374 | ✅ |
| Brussels | BE | 50.850 | 4.352 | — |
| Copenhagen | DK | 55.676 | 12.568 | — |
| Dublin | IE | 53.350 | -6.260 | — |
| Oslo | NO | 59.914 | 10.752 | — |
| Helsinki | FI | 60.170 | 24.938 | — |
| Prague | CZ | 50.076 | 14.438 | — |
| Budapest | HU | 47.498 | 19.040 | ✅ |
| Zurich | CH | 47.377 | 8.542 | — |
| Bucharest | RO | 44.427 | 26.103 | — |

The new 10 cities are operational-dashboard scope only. They are intentionally
absent from `transform/seeds/forecast_city_allowlist.csv`, so their raw rows do
not enter forecast-vintage staging, calendar-day ML training/features, or
forecast serving. Expanding `config/cities.csv` therefore does not expand the
beta forecast page. This vintage isolation prevents cross-run mixing; it does
not make the legacy hourly timestamps exact UTC instants.

Of the additions, only Vienna and Budapest have river ingestion enabled. During
the expansion review, their resolved city-centre GloFAS cells exceeded the
mart's `>50 m³/s` velocity gate. The other eight additions were disabled
because the reviewed cell was below that gate or not representative of the
intended urban river. This records a configuration decision, not continuing
hydrological validation; the selected cells must be rechecked before treating
them as authoritative river coverage.

### Operational city onboarding contract

Adding another operational city is a coordinated configuration/data change:

1. add one active, uniquely ordered row to `config/cities.csv`, including its
   IANA time zone and an explicit `river_enabled` decision;
2. add the matching row to `transform/seeds/city_signal_monitoring.csv`; Heat,
   Wind, Rain and AQ follow the all-city ingestion contract, while River must
   exactly match `river_enabled`;
3. generate the candidate's 12 monthly operational baselines into temporary
   review files with `transform/scripts/generate_city_monthly_normals.py`;
4. review the returned source grid, completeness, values and checksums, then
   merge the approved rows and update the provenance manifest;
5. run `make validate-cities`; the PR-to-`dev` CI then runs the validator and
   normals-generator unit-test suites plus a credential-free `dbt parse`;
6. rebuild and deploy the ingestion image, wait for the Cloud Run execution,
   and run dbt seed/run/test; and
7. verify that the refreshed operational marts and API expose the new city and
   the expected monitored/unmonitored factor states.

Do not add the city to `forecast_city_allowlist.csv` as a side effect. Forecast
eligibility changes the retrieval-vintage feature vocabulary, training snapshot,
artifact contract, backend serving scope and frontend selector, so it requires
a separate validation and release decision. That change must keep the dbt seed,
`backend/app/ml_pipeline.py::ALL_CITIES`, the frontend forecast-city constant
and their contract tests synchronized; none of them derives automatically from
the operational registry.

---

## APIs & Data Retrieved

The scheduled Cloud Run job actively calls four Open-Meteo endpoint families,
formats the responses as JSON, and streams them into the `raw` BigQuery dataset.
Flood is called only for river-enabled cities. A fifth CMIP6 client exists but
is not invoked by `ingest/main.py`. Because active tables are time-partitioned,
no data is overwritten; historical forecast vintages accumulate over time.

The hourly row counts below are configured expectations, not validated source
contracts. They assume 24 distinct provider timestamps per civil day. Partial
responses and any 23/25-hour daylight-saving-time representation can produce a
different count; the loader inserts the response it receives.

### 1. Weather Forecast (`raw.weather_forecast_hourly`)
- **Endpoint**: `api.open-meteo.com/v1/forecast`
- **Cadence**: Every 12 hours (all cities)
- **Time Window**: Next 7 Days (Hourly) = **168 rows per city per run**
- **Variables Retrieved**:
  - `temperature_2m` (°C at 2 meters)
  - `precipitation_mm` (mm/hour)
  - `wind_speed_10m` (km/h)
  - `wind_gusts_10m` (km/h)
  - `weather_code` (WMO Weather interpretation codes)

### 2. Air Quality (`raw.air_quality_hourly`)
- **Endpoint**: `air-quality-api.open-meteo.com/v1/air-quality`
- **Cadence**: Every 12 hours (all cities)
- **Time Window**: Next 5 Days (Hourly) = **120 rows per city per run**
- **Variables Retrieved**:
  - `european_aqi` (European Air Quality Index, 0–500 scale)
  - `pm2_5` (Particulate Matter < 2.5 µm in µg/m³)
  - `pm10` (Particulate Matter < 10 µm in µg/m³)
  - `nitrogen_dioxide` (NO₂ in µg/m³)
  - `o3` (Ozone in µg/m³)

### 3. River Discharge (`raw.flood_daily`)
- **Endpoint**: `flood-api.open-meteo.com/v1/flood`
- **Cadence**: Every 12 hours (river-enabled cities only — Paris, Amsterdam,
  Warsaw, Vienna and Budapest)
- **Time Window**: Next 7 Days (Daily) = **7 rows per city per run**
- **Variables Retrieved**:
  - `river_discharge_m3s` (GloFAS river discharge in m³/s at roughly 5 km grid
    resolution; the selected grid cell is not proof that it represents the
    intended urban river)

### 4. Historical Weather — Open-Meteo Archive/Reanalysis (`raw.historical_weather_daily`)
- **Endpoint**: `archive-api.open-meteo.com/v1/archive`
- **Cadence**: Every 12 hours (all cities)
- **Time Window**: Rolling 7-day window (`today-12` to `today-6`) = **7 rows
  per city per run**
- **Note**: Archive/reanalysis products have a publication lag. The fetch window
  is deliberately offset to reduce the chance of ingesting partial recent data;
  source completeness should still be checked rather than assumed. The request
  does not currently pin `models=era5`, and the loader does not retain the
  returned source model/version, so exact ERA5 provenance is not established
  per ingested row.
- **Variables Retrieved**:
  - `temperature_2m_mean` (Daily mean temperature in °C)
  - `temperature_2m_max` (Daily maximum temperature in °C)
  - `temperature_2m_min` (Daily minimum temperature in °C)
  - `precipitation_sum_mm` (Total daily precipitation in mm)
  - `wind_speed_10m_max` (Maximum daily wind speed in km/h)

### 5. Climate Projections — CMIP6 (implemented, scheduled fetch disabled)

- **Scheduled status**: Disabled; `ingest/main.py` does not currently invoke the
  fetch or loader, so no monthly rows or table creation should be expected
- **Endpoint**: `climate-api.open-meteo.com/v1/climate`
- **Guard if invoked directly**: 1st calendar day only. Because this guard is
  not run-idempotent, strengthen it or use a separate schedule before enabling
  this source under the twice-daily cadence.
- **Time Window**: Next 10 years (Daily) = **~3,650 rows per city per month**
- **Model**: `MRI_AGCM3_2_S` (high-resolution atmospheric model)
- **Variables Retrieved**:
  - `temperature_2m_max` (Projected daily maximum temperature in °C)
  - `temperature_2m_min` (Projected daily minimum temperature in °C)
  - `precipitation_sum_mm` (Projected total daily precipitation in mm)
  - `wind_speed_10m_max` (Projected maximum daily wind speed in km/h)

---

## Nominal Scheduled Volume Summary

| Source | Rows/city/run | Cities | Runs/day | Rows/run | Rows/day |
|---|---:|---:|---:|---:|---:|
| Weather Forecast | 168 | 20 | 2 | 3,360 | 6,720 |
| Air Quality | 120 | 20 | 2 | 2,400 | 4,800 |
| River Discharge | 7 | 5 | 2 | 35 | 70 |
| Historical archive/reanalysis | 7 | 20 | 2 | 140 | 280 |
| Climate (CMIP6) | ~3,650 | 20 | 0 scheduled | ~73,000 if invoked | 0 scheduled |
| **Active scheduled total** | | | | **~5,935** | **~11,870** |

The two active runs append approximately 11,870 raw rows per UTC day. Forecast
windows overlap intentionally, and the daily river/archive sources normally
repeat most or all of the same valid dates in the second run. Run IDs preserve
those retrievals as separate vintages; this is append volume, not a count of
unique forecast or observation times.

---

## Ingestion Metadata

Every row inserted into BigQuery is stamped with two metadata fields for traceability:

| Field | Type | Description |
|---|---|---|
| `ingestion_run_id` | `STRING` | UUID v4 unique to each pipeline run |
| `ingested_at_utc` | `TIMESTAMP` | UTC timestamp when the run started |

These fields support staging deduplication and retrieval-run lineage. They are
not complete source provenance: `ingested_at_utc` is captured once at the start
of the whole job, and the raw schema does not retain the provider's model issue
time, a per-city request time, response headers or source-version metadata.

### Hourly valid-time caveat

For hourly weather and AQ, the fetcher requests each city's local time zone and
stores the offset-free provider clock text in the legacy `valid_ts_utc` field
before loading it into a BigQuery `TIMESTAMP`. BigQuery therefore interprets
the provider-local clock as UTC; despite its name and type, the field is not a
trustworthy UTC instant. Exact UTC event-time, lead-hour, cross-city ordering
and DST claims are therefore invalid under the current schema.

`DATE(valid_ts_utc)` still preserves the provider's local calendar-date text in
ordinary responses. Day-level aggregation and day-number horizons remain
usable for normal scheduled runs, subject to the documented 23/25-hour DST
coverage behavior and the per-city request-midnight edge case. Correcting the
instant requires retaining an offset-aware provider timestamp and explicitly
preserving this local-calendar contract downstream.

## Delivery and Retry Semantics

Each city/source request is attempted once by the application with a request
timeout; there is no application-level retry or backoff. A source failure is
logged and processing continues with the remaining city/source pairs. If any
rows were inserted, the run is classified as a partial failure and still
attempts dbt; after the transform attempt it exits non-zero so Cloud Run and a
waiting deploy cannot mistake the partial load for success. Terraform sets the
Cloud Run task's `max_retries` to `0`: a failed whole-job execution is not
automatically replayed because another run would append overlapping raw rows
under a new run ID. After correcting the cause, rerun the job deliberately.

Raw writes use BigQuery streaming inserts without an application-supplied
idempotency key. Re-executing the job creates a new `ingestion_run_id` and can
append overlapping rows. That is expected in Bronze. The active operational v2
path first selects one most-recent `ingestion_run_id` shared across the raw
source families, then uses only rows from that exact run; it deliberately does
not fill a missing city/source from an older run. Missing payloads therefore
remain NULL with explicit coverage/availability downstream. The separate ML
vintage path retains individual retrievals. The older `stg_latest_*` path
remains only for temporary unsuffixed-mart rollback compatibility. Do not
interpret raw row count as a count of unique forecast instants.

### Unresolved active-snapshot risk

The exact-run selector does not consume a durable completed-run manifest. Any
new `ingestion_run_id` with at least one row in any active raw source family is
eligible, even while that run is in progress or if it later exits as failed.
When dbt rebuilds the selector, that partial run can become the active
operational snapshot. Exact-run joins then expose its missing city/source
payloads as unavailable; they do not restore them from the previous healthy
run. A zero-row failed run, by contrast, leaves the previous snapshot selected.

A non-zero Cloud Run exit does not roll back raw inserts or a mart rebuild that
already completed. Current deployment and staging-readiness gates check items
such as snapshot age, run coherence, schemas and the 20-city spine, but do not
require every expected city/source payload or a minimum availability level.
They therefore do not prove that the active snapshot is source-complete. Run
ID/timestamp fields and the frontend's 36-hour stale warning improve visibility
only; durable run state and an atomic promotion gate remain future hardening.

## Table Auto-Creation

The active Python loaders use `client.create_table(exists_ok=True)` to create
their four raw tables on first successful use. They do **not** create the `raw`
dataset itself; it must already exist in the configured BigQuery location, as
described in [Doc 1](1-bootstrap-initialization.md). The optional
`climate_projections_daily` table is not auto-created while the CMIP6 call
remains disabled.

---

## Post-Ingestion: Automated dbt Run

Unless the run records source errors and inserts zero rows, the Cloud Run Job
invokes `dbt seed` and then `dbt run` to rebuild the Silver staging views and
Gold mart relations in the same execution. Partial ingestion therefore still
starts the transform step and can publish that partial run as the active
snapshot before the job exits non-zero. An unusual zero-row run with no
recorded exception starts the transform step too.

### How it works

```
Cloud Scheduler (06:00 and 18:00 UTC)
    → Cloud Run Job starts
        → [1] Ingest: fetch 4 active source families → raw.* tables
        → [2] Transform: dbt seed + dbt run
            → exact-run stg.*_v2 → active mart_city_score_*_v2
            → legacy unsuffixed relations remain available for rollback
    → Job exits
```

The `run_dbt()` function in `main.py` invokes dbt as subprocesses using the
`transform/` directory bundled inside the Docker image and the `prod` target:

```python
subprocess.run([
    "dbt", "--no-use-colors", "seed",
    "--project-dir", "/app/transform",
    "--profiles-dir", "/app/transform",
    "--target", "prod",
], check=True)

subprocess.run([
    "dbt", "--no-use-colors", "run",
    "--project-dir", "/app/transform",
    "--profiles-dir", "/app/transform",
    "--target", "prod",
], check=True)
```

Authentication is handled automatically via the Cloud Run Job's service account
— no JSON key file is required (`method: oauth` in `profiles.yml`). The
committed `dev` and `prod` dbt targets currently have the same settings;
environment isolation comes from the active credentials and
`GCP_PROJECT_ID`, not from selecting the target name.

### Failure behaviour

| Scenario | Outcome |
|---|---|
| All active fetch/insert attempts fail (errors and 0 rows inserted) | Job exits with code 1 — dbt is **not** triggered |
| Ingestion partial success (some rows inserted) | dbt seed/run is attempted against the available data and can select the partial run as active; the job then exits with code 1, without rolling back published warehouse state |
| `dbt seed` or `dbt run` fails | The subprocess failure propagates and the Cloud Run execution exits non-zero; already inserted raw rows remain durable |
| dbt tests | **Not run** by the scheduled ingestion job; run `make dbt-test` or `dbt test` separately |

`make deploy` executes this job with `--wait`; any non-zero outcome stops the
deploy. After a successful job it runs a final local `dbt seed`, `dbt run` and
`dbt test`. Each Scheduler-triggered execution still omits tests, so test and
freshness monitoring remain separate operational checks.

For the v2 availability rollout, `make deploy` is the data-plane prerequisite:
it creates the v2 staging and mart relations while the legacy application can
continue reading unsuffixed marts. The staging application workflow then
queues the compatibility frontend, validates the v2 schemas and 20-city
coverage, selected-run coherence and 36-hour snapshot age while it builds, then
marker-confirms the frontend before queueing and exact-release-confirming the v2
backend. Both Railway submissions use detached mode, but the service cutovers
remain ordered rather than parallel.

### Verifying in logs

In GCP Console → **Cloud Run** → **Jobs** → `clima-sentinel-ingest` → select an execution → **Logs**, you will see:

```
── dbt run starting ──────────────────────────────────────────────
Running with dbt=1.x.x
...
Completed successfully
── dbt run complete ✓ ──────────────────────────────────────────
```

If dbt fails, the log will show:
```
── dbt run FAILED (exit 1) — mart tables may be stale. Check logs above for details.
```

## Automated-Validation Boundary

The pull-request workflow validates the checked-in city registry, monthly
normals, signal-monitoring seed and frozen forecast allowlist; unit-tests
ingestion failure propagation; performs a credential-free `dbt parse`; and
builds both backend and ingestion images. It does not run live ingestion or an
authenticated `dbt run`, `dbt test` or source-freshness check. A successful
parse validates project structure and SQL/Jinja compilation, not raw schemas or
warehouse data. Transform changes still require authenticated BigQuery/dbt
validation. The scheduled job propagates ingest/dbt failures but omits tests
and source freshness checks. Neither this validation nor the current
staging-readiness gate proves that every expected city/source payload is
present in the selected run.
