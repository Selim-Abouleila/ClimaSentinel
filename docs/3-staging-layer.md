# 3. Staging Layer (Silver)

The staging layer transforms raw, append-only ingested data into clean, deduplicated, and harmonized views in BigQuery. It uses **dbt** (data build tool) to manage SQL transformations with dependency ordering, schema tests, and auto-generated documentation.

## Purpose

The `raw.*` tables accumulate overlapping data on every ingestion run (e.g., 168 hourly weather rows per city per day, with 6 days of overlap between consecutive runs). The layer now exposes two intentionally different paths: the existing `stg_latest_*` path supports the operational dashboard, while the parallel `*_vintage` path preserves what was available at each ingestion run for point-in-time ML training and serving.

Before computing operational tipping scores, we need to:

1. **Deduplicate** — Keep only the freshest forecast for each `(city_id, timestamp)` pair
2. **Apply legacy null handling** — The operational daily aggregates coalesce
   some missing precipitation, wind and pollutant readings to zero
3. **Harmonize grain** — Roll hourly tables down to daily summaries so all signals share the same `(city_id, date)` key
4. **Unify** — JOIN all signals into a single `stg.city_signal_input` table for the mart layer

For point-in-time ML inputs, we instead:

1. **Preserve forecast runs** — Retain `ingestion_run_id` and `ingested_at_utc`
2. **Aggregate within a run** — Never mix forecast revisions in one daily row
3. **Use city-local calendar horizons** — Convert the UTC ingestion timestamp with the city's IANA timezone, then derive `horizon_days` with `DATE_DIFF`
4. **Preserve missingness** — Keep NULL measurements and expose reading counts
5. **Join coherently** — Join weather, AQ, and flood only from the exact same run

---

## Model Dependency Graph

```
raw.weather_forecast_hourly ──→ stg_latest_weather_hourly ──→ stg_city_daily_weather ──┐
raw.air_quality_hourly ────────→ stg_latest_air_quality_hourly → stg_city_daily_air_quality ─┤
raw.flood_daily ───────────────→ stg_latest_flood_daily ───────────────────────────────────────┤
raw.historical_weather_daily ──→ stg_latest_historical_daily ──────────────────────────────────┤
                                                                                                ▼
                                                                              stg_city_signal_input
                                                                                        │
                                                                                        ▼
                                                                              (mart layer — next)

raw.weather_forecast_hourly ──→ stg_weather_forecast_hourly_vintage ──→ stg_city_daily_weather_vintage ──┐
raw.air_quality_hourly ────────→ stg_air_quality_hourly_vintage ───────→ stg_city_daily_air_quality_vintage ┤
raw.flood_daily ───────────────→ stg_flood_daily_vintage ──────────────────────────────────────────────────┤
                                                                                                           ▼
                                                                                         stg_city_signal_vintage
                                                                                         (point-in-time ML marts)
```

---

## Models

### Static Seeds (1)

Static configuration data loaded directly into BigQuery tables via `dbt seed`.

| Seed | Description | Source |
|---|---|---|
| `city_monthly_normals` | Checked-in city/month lookup described in repository history as 2014-2023 temperature, rain and wind averages. The Gold layer currently uses its maximum-temperature value as the Heat baseline. | `transform/seeds/city_monthly_normals.csv` |

The repository does not currently contain the query or script that generated
this seed, nor the exact Open-Meteo model/version, coordinates, retrieval date
and missing-data rules used to produce it. The CSV is therefore versioned
configuration, but it is not independently reproducible from the repository.
Any refresh must define one unique key for every supported city/month (currently
120), and record those inputs before old and new scores or model metrics are
compared.

### Deduplication Views (4)

These views apply a `ROW_NUMBER() OVER (PARTITION BY ... ORDER BY ingested_at_utc DESC)` pattern to keep only the most recently ingested row for each natural key.

| Model | Source | Dedup Key |
|---|---|---|
| `stg_latest_weather_hourly` | `raw.weather_forecast_hourly` | `(city_id, valid_ts_utc)` |
| `stg_latest_air_quality_hourly` | `raw.air_quality_hourly` | `(city_id, valid_ts_utc)` |
| `stg_latest_flood_daily` | `raw.flood_daily` | `(city_id, date)` |
| `stg_latest_historical_daily` | `raw.historical_weather_daily` | `(city_id, date)` |

This is a latest-value operational projection, not an immutable as-of ledger.
If duplicate rows share the same natural key and identical
`ingested_at_utc`, these four views do not define a secondary tie-breaker. Use
the vintage path for retrieval-level lineage rather than treating
`stg_latest_*` as audit history.

### Aggregation Views (2)

These views roll up deduplicated hourly data into daily summaries.

| Model | Source | Aggregations |
|---|---|---|
| `stg_city_daily_weather` | `stg_latest_weather_hourly` | AVG/MAX/MIN temp, SUM precip, MAX wind, MAX weather code |
| `stg_city_daily_air_quality` | `stg_latest_air_quality_hourly` | AVG/MAX AQI, AVG PM2.5/PM10/NO₂/O₃ |

### Unified Signal Table (1)

| Model | Description |
|---|---|
| `stg_city_signal_input` | Joins weather + air quality + river + historical into one row per `(city_id, date)` |

**Operational nullability rules:**

- Weather anchors the row, but the legacy daily aggregation converts missing
  precipitation and wind readings to zero. Temperature aggregates can still be
  NULL if all source readings are missing.
- Air-quality columns can be NULL when there is no joined AQ row. Within an
  existing AQ day, the legacy averages convert missing pollutant readings to
  zero.
- `river_discharge_m3s`: NULL for non-river-enabled cities (7 of 10)
- `hist_*` columns: NULL for dates outside the ERA5 lag window (most recent 6 days)

These rules belong only to the legacy operational path. They can suppress a
risk factor when source measurements are missing, so this path must not be used
as evidence that a missing observation was truly zero.

> **Note:** CMIP6 climate projections are excluded from
> `city_signal_input`. Their scheduled fetch is currently disabled, and no
> staging or mart model consumes `raw.climate_projections_daily`.

### Forecast-Vintage Views (6)

These views preserve every ingestion run. `ingested_at_utc` is the ingestion-run start timestamp used as ClimaSentinel's availability proxy; it is not Open-Meteo's model issue or initialization timestamp. `forecast_origin_time_zone` records the IANA timezone used to convert that UTC timestamp into the city's local `forecast_origin_date`.

| Model | Grain | Purpose |
|---|---|---|
| `stg_weather_forecast_hourly_vintage` | `(ingestion_run_id, city_id, valid_ts_utc)` | Retains every hourly weather forecast revision |
| `stg_city_daily_weather_vintage` | `(ingestion_run_id, city_id, valid_date)` | Aggregates weather inside one retrieval only |
| `stg_air_quality_hourly_vintage` | `(ingestion_run_id, city_id, valid_ts_utc)` | Retains every hourly AQ forecast revision |
| `stg_city_daily_air_quality_vintage` | `(ingestion_run_id, city_id, valid_date)` | Aggregates AQ inside one retrieval only |
| `stg_flood_daily_vintage` | `(ingestion_run_id, city_id, valid_date)` | Retains every river-discharge forecast revision |
| `stg_city_signal_vintage` | `(ingestion_run_id, city_id, valid_date)` | Same-run weather/AQ/flood signal view anchored on weather |

The vintage path does not join ERA5. ERA5 is published later and belongs to a future realized-outcome/label path, not to the forecast snapshot that was available at prediction time.

**Vintage nullability and coverage rules:**

- Missing measurements remain NULL; staging never turns missing AQ, rain, wind, or river values into zero.
- Per-variable reading counts and source-presence flags make partial responses observable.
- AQ and flood never fall back to a different run after a partial ingestion failure.
- Flood is legitimately absent for non-river-enabled cities.
- AQ has a five-day window while weather and flood have seven-day windows.
- Unknown city IDs fail during vintage-model evaluation until an IANA timezone is configured; they never silently fall back to UTC.

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

All staging models are materialized as **views** (not tables). This means:
- ✅ No duplicated model-data storage for the views themselves
- ✅ Reflects the rows currently stored in `raw` on every query
- ✅ No data refresh is needed after new raw rows arrive
- ⚠️ Definition changes still require `dbt run` to replace the views
- ⚠️ Every query can rescan upstream data and incur BigQuery query cost
- ⚠️ Slightly slower queries (acceptable for silver; mart layer uses tables)

---

## Running the Models

### Via `make deploy` (recommended)

Staging views are created automatically as part of `make deploy`:

```
make deploy  →  build/push image  →  terraform apply  →  dbt seed + run + test
```

No separate dbt command or profile configuration needed — the profile reads `GCP_PROJECT_ID` and `GCP_REGION` from your `.env` file automatically via dbt's `env_var()`.

> **Clean-room limitation:** on a brand-new project, create the `raw` dataset
> first. The initial `make deploy` can apply the infrastructure and then fail in
> dbt because the four active raw source tables do not exist until the ingestion
> job runs once. Follow the first-deployment sequence in
> [Doc 1](1-bootstrap-initialization.md).

### Prerequisites (first time only)

```bash
pip install -r transform/requirements.txt
gcloud auth application-default login
```

### Standalone Commands

| Command | Description |
|---|---|
| `make deploy` | Full pipeline: build + terraform + dbt run + test |
| `make dbt-stg` | Run staging models only |
| `make dbt-run` | Run all models (stg + mart) |
| `make dbt-test` | Run schema and singular data tests |

### From the transform directory

```bash
cd transform
set -a
source ../.env
set +a
dbt run --profiles-dir . --select stg        # Build staging views
dbt test --profiles-dir . --select stg       # Run schema + singular staging tests
dbt run --profiles-dir . --select tag:forecast_vintage
dbt test --profiles-dir . --select tag:forecast_vintage
dbt docs generate --profiles-dir . && dbt docs serve --profiles-dir .
```

dbt's `env_var()` reads the process environment; it does not parse `.env`
itself. The Makefile exports `.env` automatically, while direct dbt commands
need the explicit export above (or equivalent shell/CI configuration).

---

## Schema Tests

Core schema tests are defined in `_stg_models.yml` and `_stg_vintage_models.yml`. Singular tests in `transform/tests` validate the composite vintage grains, city-local origin/horizon derivation, one timestamp per run, raw retry-payload consistency, and the weather-anchored unified key set. The unified lineage test validates exact-vintage source presence, timestamps, coverage metadata, and nullable-value propagation. Coverage anomalies are warnings during the initial raw-history audit rather than filters or hard failures.

The scheduled Cloud Run ingestion job runs `dbt seed` and `dbt run`, but not
`dbt test`. These contracts are enforced only when `make dbt-test`, `dbt test`
or another validation workflow invokes them; a green scheduled execution is
not evidence that the tests passed.

The checked-in GitHub Actions workflows also do not compile or test this dbt
project. In addition, `_stg_sources.yml` has no dbt source-freshness policy, so
`dbt test` does not establish that raw data is recent. A green pull request and
a passing warehouse test suite are separate signals; freshness needs an
explicit operational check.

The hard lineage test deliberately does not compare `AVG`/`SUM`-derived `FLOAT64` values by independently rereading the daily views. All staging relations are views, so BigQuery can expand those reductions separately through `stg_city_signal_vintage` and through the test's source references; floating-point reduction and the final two-decimal rounding can then depend on the query plan. Deterministic `MAX`/`MIN` and direct-value projections remain hard-checked. Raw conflicting payloads also fail `assert_forecast_vintage_raw_payloads_consistent`, while aggregate NULL propagation remains part of the lineage contract.

| Model | Column | Test |
|---|---|---|
| All 7 operational models | `city_id` | `not_null` |
| Hourly models | `valid_ts_utc` | `not_null` |
| Daily models | `date` | `not_null` |
| Vintage models | Lineage and grain columns | `not_null` |
| All vintage models | Composite run/city/valid key | Singular uniqueness test |

For staging approval, all hard vintage tests must pass. The coverage audit may warn for preserved historical partial responses, older AQ windows, DST days, or off-schedule source-window differences; every warning must be explainable rather than removed or imputed in staging.
