# 3. Staging Layer (Silver)

The staging layer transforms raw, append-only ingested data into clean,
deduplicated and harmonized relations in BigQuery. It uses **dbt** (data build
tool) to manage SQL transformations with dependency ordering, schema tests and
auto-generated documentation.

## Purpose

The `raw.*` tables accumulate overlapping data on every ingestion run (e.g.,
nominally 168 hourly weather rows per city per run and 336 across the two
scheduled runs per UTC day, with heavily overlapping forecast windows). The
layer exposes three intentionally different paths:

- the active `*_v2` operational path selects one exact ingestion run, preserves
  missingness, and creates a configured 20-city/date spine;
- the unsuffixed `stg_latest_*` path remains temporarily for legacy mart
  rollback compatibility and is not the active dashboard contract; and
- the parallel `*_vintage` path preserves every eligible ingestion run for
  point-in-time ML training and serving.

Before computing active operational v2 tipping scores, we:

1. **Select one run** — `stg_operational_run_v2` chooses the most recent
   `ingestion_run_id` across the active raw source families; v2 never borrows a
   missing city/source payload from an older run.
2. **Preserve missing measurements** — Exact-run daily aggregates leave
   all-null inputs as NULL and retain per-factor non-null reading counts.
3. **Build the operational spine** — Cross the 20-row
   `city_signal_monitoring` seed with selected-run dates plus UTC today through
   D+2, so a missing weather payload does not remove a configured city.
4. **Apply the monitoring contract** — Distinguish a source that is not
   configured from a monitored source that is temporarily unavailable.
5. **Unify** — Publish one exact-run row per `(city_id, date)` in
   `stg.city_signal_input_v2` for the active v2 mart layer.

For point-in-time ML inputs, we instead:

1. **Preserve forecast runs** — Retain `ingestion_run_id` and `ingested_at_utc`
2. **Aggregate within a run** — Never mix forecast revisions in one daily row
3. **Use city-local calendar horizons** — Convert the UTC ingestion timestamp with the city's IANA timezone, then derive `horizon_days` with `DATE_DIFF`
4. **Preserve missingness** — Keep NULL measurements and expose reading counts
5. **Join coherently** — Join weather, AQ, and flood only from the exact same run

---

## Model Dependency Graph

```
raw.weather_forecast_hourly ─┐
raw.air_quality_hourly ──────┼──→ stg_operational_run_v2 ─┬──→ stg_city_daily_weather_v2 ─────┐
raw.flood_daily ─────────────┤                            ├──→ stg_city_daily_air_quality_v2 ─┤
raw.historical_weather_daily ─┘                           └──→ stg_flood_daily_v2 ────────────┤
city_signal_monitoring ───────────────────────────────────────────────────────────────────────┤
                                                                                              ▼
                                                                            stg_city_signal_input_v2
                                                                                      │
                                                                                      ▼
                                                                            active v2 mart layer

stg_latest_* ──→ unsuffixed staging/marts (temporary legacy rollback only)

raw.weather_forecast_hourly ──→ stg_weather_forecast_hourly_vintage ──→ stg_city_daily_weather_vintage ──┐
raw.air_quality_hourly ────────→ stg_air_quality_hourly_vintage ───────→ stg_city_daily_air_quality_vintage ┤
raw.flood_daily ───────────────→ stg_flood_daily_vintage ──────────────────────────────────────────────────┤
                                                                                                           ▼
                                                                                         stg_city_signal_vintage
                                                                                         (point-in-time ML marts)
```

---

## Models

### Static Seeds (3)

Static configuration data loaded directly into BigQuery tables via `dbt seed`.

| Seed | Description | Source |
|---|---|---|
| `city_monthly_normals` | Structurally validated 240-row lookup: one temperature, precipitation and wind baseline row for each of 12 months across 20 operational cities. The Gold layer uses its maximum-temperature value as the Heat baseline. | `transform/seeds/city_monthly_normals.csv` |
| `forecast_city_allowlist` | Frozen original 10-city/timezone contract for forecast-vintage staging and point-in-time feature, training and serving outputs. The other 10 operational cities remain outside that path. | `transform/seeds/forecast_city_allowlist.csv` |
| `city_signal_monitoring` | One row per active operational city declaring whether Heat, Wind, Rain, Air Quality and River are monitored. Weather and AQ are enabled for all 20 cities; River mirrors `config/cities.csv:river_enabled`. | `transform/seeds/city_signal_monitoring.csv` |

`transform/scripts/generate_city_monthly_normals.py` generated the expansion's
120 rows from the Open-Meteo Historical Weather endpoint with
`models=best_match`, each city's IANA timezone, and the fixed interval
2014-01-01 through 2023-12-31. It computes the arithmetic mean of every finite
daily temperature mean/maximum, precipitation sum and maximum wind value within
each local calendar month, rejects missing or non-finite source values, and
rounds outputs to two decimal places.
`transform/seeds/city_monthly_normals.provenance.json` records the endpoint,
model, 2026-08-01 retrieval date, interval, variables, units and aggregation
policy.

The original cities' 120 rows are intentionally retained from the historical
seed. They predate the generator and cannot be claimed as exactly regenerable;
Open-Meteo's Best Match archive can also be revised after retrieval. The
generator/provenance pair makes the new expansion procedure auditable without
misrepresenting the legacy half of the seed.

The standard-library city validator checks unique city/month keys, exactly 12
months for every active city, finite physical ranges, registry consistency,
the frozen original forecast IDs, and exact monitoring-seed alignment before
deployment. It rejects a missing active city, a disabled weather/AQ factor, or
a River monitoring value that differs from `river_enabled`. dbt adds seed-level
not-null/unique checks and warehouse-side monitoring and normal-completeness
contracts.

### Active Exact-Run Operational v2 Models (5)

| Model | Grain | Purpose |
|---|---|---|
| `stg_operational_run_v2` | one row | Selects the most recent exact `ingestion_run_id` across active raw source families and records source-presence/count metadata |
| `stg_city_daily_weather_v2` | `(city_id, date)` | Aggregates weather from only the selected run and retains temperature, rain and wind reading counts |
| `stg_city_daily_air_quality_v2` | `(city_id, date)` | Aggregates AQ from only the selected run and retains AQ reading counts |
| `stg_flood_daily_v2` | `(city_id, date)` | Projects flood rows from only the selected run |
| `stg_city_signal_input_v2` | `(city_id, date)` | Crosses monitoring configuration with selected-run dates plus UTC today through D+2, then left-joins exact-run weather, AQ and flood inputs |

The D+2 spine supports the current mart's today/tomorrow evaluation and the
next-day Heat/River velocity rules without making weather the row anchor. Its
configured city dimension is the 20-row `city_signal_monitoring` seed, so every
operational city remains observable even when the selected run has no weather
rows for it.

`stg_operational_run_v2` currently selects by raw run/timestamp evidence; no
durable completed-run manifest exists. A failed run can therefore leave the
prior snapshot in service, and an overlapping/in-progress run can briefly be
selected. Downstream run ID/timestamp fields plus the frontend's 36-hour stale
warning improve visibility but do not provide transactional run auditing.

**Operational v2 nullability, coverage and monitoring rules:**

- The exact-run join never falls back to a prior ingestion run.
- Daily aggregates ignore individual NULLs, remain NULL when all required
  measurements are NULL, and expose reading counts for explicit coverage.
- A factor score is eligible only when its monitored flag is true and all
  required inputs have full coverage. Partial or absent input remains NULL and
  becomes `unavailable` downstream.
- `river_monitored=false` becomes `not_monitored`; a monitored River feed with
  no selected-run value becomes `unavailable`.
- A complete, monitored measurement whose rule evaluates to zero remains the
  numeric score `0.0`; it is never confused with missing input.

### Temporary Legacy Rollback Staging Views

The unsuffixed relations `stg_latest_weather_hourly`,
`stg_latest_air_quality_hourly`, `stg_latest_flood_daily`,
`stg_latest_historical_daily`, `stg_city_daily_weather`,
`stg_city_daily_air_quality` and `stg_city_signal_input` remain only to support
the unsuffixed legacy marts during the rollout. They retain their existing
latest-per-natural-key behavior and legacy schema. They are not the active v2
dashboard contract and must not be assumed to expose v2 availability or
coverage columns.

Use the vintage path for retrieval-level lineage rather than treating either
the legacy latest views or the rebuilt operational v2 table as an immutable
as-of history.

> **Note:** CMIP6 climate projections are excluded from
> `city_signal_input_v2`. Their scheduled fetch is currently disabled, and no
> staging or mart model consumes `raw.climate_projections_daily`.

### Forecast-Vintage Views (6)

These views preserve every ingestion run for cities in
`forecast_city_allowlist`. The three entry models join that seed before their
forecast rows are ranked, so a new operational dashboard city is excluded from
point-in-time forecast features, training and serving by default. The allowlist
remains the original Paris, London, Madrid, Berlin, Rome, Amsterdam, Athens,
Warsaw, Lisbon and Stockholm set; Vienna, Brussels, Copenhagen, Dublin, Oslo,
Helsinki, Prague, Budapest, Zurich and Bucharest are operational-only.
`ingested_at_utc` is the ingestion-run start timestamp used as ClimaSentinel's
availability proxy; it is not Open-Meteo's model issue or initialization
timestamp.
`forecast_origin_time_zone` comes from the allowlist and is used to convert
that UTC timestamp into the city's local `forecast_origin_date`.

| Model | Grain | Purpose |
|---|---|---|
| `stg_weather_forecast_hourly_vintage` | `(ingestion_run_id, city_id, valid_ts_utc)` | Retains every hourly weather forecast revision |
| `stg_city_daily_weather_vintage` | `(ingestion_run_id, city_id, valid_date)` | Aggregates weather inside one retrieval only |
| `stg_air_quality_hourly_vintage` | `(ingestion_run_id, city_id, valid_ts_utc)` | Retains every hourly AQ forecast revision |
| `stg_city_daily_air_quality_vintage` | `(ingestion_run_id, city_id, valid_date)` | Aggregates AQ inside one retrieval only |
| `stg_flood_daily_vintage` | `(ingestion_run_id, city_id, valid_date)` | Retains every river-discharge forecast revision |
| `stg_city_signal_vintage` | `(ingestion_run_id, city_id, valid_date)` | Same-run weather/AQ/flood signal view anchored on weather |

The vintage path does not join lagged archive/reanalysis outcomes. Those values
are published later and belong to the realized-outcome/label path, not to the
forecast snapshot that was available at prediction time.

**Vintage nullability and coverage rules:**

- Missing measurements remain NULL; staging never turns missing AQ, rain, wind, or river values into zero.
- Per-variable reading counts and source-presence flags make partial responses observable.
- AQ and flood never fall back to a different run after a partial ingestion failure.
- Flood is legitimately absent for non-river-enabled cities.
- AQ has a five-day window while weather and flood have seven-day windows.
- City IDs absent from `forecast_city_allowlist` are excluded from all three vintage entry models; they never silently enter point-in-time forecast features, training or serving outputs.

`has_24_hour_coverage` means exactly 24 distinct stored timestamps, not
"complete for the local civil day." If an upstream response represents a DST
transition with 23 or 25 distinct timestamps, the flag is false even when that
response is complete for that day. The ML feature mart requires this flag for
weather on every Horizon 0-4 date, so such a vintage is not canonical for
training or serving. The current warehouse does not implement a
timezone-aware 23/24/25-hour eligibility rule.

> **Timestamp caveat:** despite its name and BigQuery `TIMESTAMP` type,
> `valid_ts_utc` is not currently a trustworthy UTC instant. The fetcher
> requests city-local timestamps and stores the provider's offset-free strings
> in that field. Calendar-day horizons are anchored to the city-local ingestion
> date, including off-schedule runs that cross local midnight, but consumers
> must not use the field for precise lead-hour, cross-time-zone or DST
> calculations. Those uses require an ingestion change that preserves the
> provider timestamp offset. When the field is corrected to contain a true UTC
> instant, `valid_date` must also change to
> `DATE(valid_ts_utc, forecast_origin_time_zone)` so the calendar contract
> remains local.

`ingested_at_utc` is currently one timestamp captured at the start of the whole ingestion run. If an unusually long run begins before a city's local midnight but fetches that city after midnight, the raw schema cannot reconstruct the later per-city request date. Normal scheduled runs are short enough to avoid this edge case; a future ingestion revision should persist provider issue time or a per-city request timestamp.

The local-origin rule matters for retries and manual runs. For example, an ingestion at `23:31 UTC` on July 4 is already July 5 in the configured European cities. Its weather window must remain Day `0–6`, not be mislabeled as Day `1–7`. Flood rows whose provider date is already in the local past remain visible in the flood ledger with a negative horizon, but cannot join the weather-anchored unified view unless their local valid date and horizon match.

---

## Materialization

`stg_operational_run_v2` is intentionally a **table**: each `dbt run` freezes
one selected operational run ID/timestamp for all downstream v2 queries. The
other staging models are **views**. Consequently:

- ✅ downstream v2 views agree on one selected run until dbt rebuilds the
  selector table;
- ✅ views avoid duplicating their transformed row sets;
- ⚠️ newly appended raw rows do not change the selected run until `dbt run`
  rebuilds `stg_operational_run_v2`;
- ⚠️ definition changes still require `dbt run`; and
- ⚠️ querying views can rescan upstream data and incur BigQuery cost.

---

## Running the Models

### Via `make deploy` (recommended)

Staging views are created automatically as part of `make deploy`:

```
make deploy  →  validate city files  →  build/push  →  terraform apply
             →  execute/wait for ingestion + embedded dbt seed/run
             →  final dbt seed + run + test
```

No separate dbt command or profile configuration needed — the profile reads `GCP_PROJECT_ID` and `GCP_REGION` from your `.env` file automatically via dbt's `env_var()`.

> **First-deploy prerequisite:** on a brand-new project, create the `raw`
> dataset first. The deploy then waits for ingestion to create the active source
> tables before its final dbt validation. Follow
> [Doc 1](1-bootstrap-initialization.md).

### Prerequisites (first time only)

```bash
pip install -r transform/requirements.txt
gcloud auth application-default login
```

### Standalone Commands

| Command | Description |
|---|---|
| `make validate-cities` | Validate the operational registry, 240-row normals seed, 20-row signal-monitoring contract, and frozen forecast allowlist |
| `make deploy` | Full GCP data pipeline: validate + build + Terraform + waited ingestion + dbt seed/run/test |
| `make dbt-stg` | Run staging models only |
| `make dbt-run` | Run all models (stg + mart) |
| `make dbt-test` | Run schema and singular data tests |

### From the transform directory

```bash
cd transform
set -a
source ../.env
set +a
dbt run --profiles-dir . --select stg        # Build staging relations
dbt test --profiles-dir . --select stg       # Run schema + singular staging tests
dbt build --profiles-dir . --select tag:forecast_vintage
dbt docs generate --profiles-dir . && dbt docs serve --profiles-dir .
```

dbt's `env_var()` reads the process environment; it does not parse `.env`
itself. The Makefile exports `.env` automatically, while direct dbt commands
need the explicit export above (or equivalent shell/CI configuration).

---

## Schema Tests

Core schema tests are defined in `_stg_models.yml` and
`_stg_vintage_models.yml`. The active operational-v2 singular tests enforce the
20-city/date spine, one coherent selected run, consistent raw payloads and exact
monitoring-seed alignment. Vintage singular tests separately validate composite
grains, city-local origin/horizon derivation, one timestamp per run, retry
payload consistency and the weather-anchored unified key set. The vintage
lineage test validates exact-vintage source presence, timestamps, coverage
metadata and nullable-value propagation. Vintage coverage anomalies are
warnings during the initial raw-history audit rather than filters or hard
failures.

The scheduled Cloud Run ingestion job runs `dbt seed` and `dbt run`, but not
`dbt test`. Ingest partial failures and dbt subprocess failures now propagate as
a failed job execution. The warehouse test contracts are enforced by `make
deploy` after a successful waited job, or by standalone `make dbt-test`/`dbt
test`; a green Scheduler-triggered execution alone is not evidence that tests
passed.

The pull-request workflow validates the checked-in registry, monthly normals,
monitoring seed and forecast scope; unit-tests ingestion failure propagation;
and performs a credential-free `dbt parse`. Parse checks project structure and
SQL/Jinja compilation but does not build or test relations against BigQuery.
In addition, `_stg_sources.yml` has no dbt source-freshness policy, so `dbt
test` does not establish that raw data is recent. A green pull request and a
passing warehouse test suite are separate signals; freshness needs an explicit
operational check.

The hard vintage-lineage test deliberately does not compare
`AVG`/`SUM`-derived `FLOAT64` values by independently rereading the daily views.
The vintage staging relations involved are views, so BigQuery can expand those
reductions separately through `stg_city_signal_vintage` and through the test's
source references; floating-point reduction and the final two-decimal rounding
can then depend on the query plan. Deterministic `MAX`/`MIN` and direct-value
projections remain hard-checked. Raw conflicting payloads also fail
`assert_forecast_vintage_raw_payloads_consistent`, while aggregate NULL
propagation remains part of the lineage contract.

| Model | Column | Test |
|---|---|---|
| Active operational v2 models | Run lineage, city/date keys and source fields | Schema tests plus singular run/spine/payload contracts |
| Legacy unsuffixed staging models | Legacy keys | Existing schema tests during rollback window |
| Hourly models | `valid_ts_utc` | `not_null` |
| Daily models | `date` | `not_null` |
| Vintage models | Lineage and grain columns | `not_null` |
| All vintage models | Composite run/city/valid key | Singular uniqueness test |

For staging approval, all hard operational-v2 and vintage tests must pass. The
vintage coverage audit may warn for preserved historical partial responses,
older AQ windows, DST days or off-schedule source-window differences; every
warning must be explainable rather than removed or imputed in staging.
