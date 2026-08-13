# Critical Interpretation and Evidence Limits

This is the governing limitation contract for ClimaSentinel's operational
score, forecast-validation claims and data lineage. Implementation detail
remains in the [ingestion](2-ingestion-pipeline.md),
[staging](3-staging-layer.md), [mart](4-mart-layer.md) and
[ML/MLOps](11-machine-learning-model.md) guides.

This document corrects how the current system may be described. It does not
repair the underlying score calibration, run promotion, timestamp storage or
source-provenance gaps.

## Status of the Tipping Score

The Tipping Score is a **Beta operational prioritization heuristic**. It is not
a physical climate tipping-point model, a calibrated event probability, a
validated severity index or an emergency-response recommendation.

The active calculation is implemented in
[`mart_city_score_history_v2.sql`](../transform/models/mart/mart_city_score_history_v2.sql):

| Component | Heuristic calculation before clipping to 0-100 |
|---|---|
| Heat | `(Tmax - monthly reference) * 5 + max(0, next-day Tmax - Tmax) * 5` |
| Wind | `max(0, gust_km_h - 40) * 2.5` |
| Rain | `precipitation_mm * 2` |
| Air quality | `(European_AQI - 40) * 1.67` |
| River | `max(0, next-day discharge change / current discharge) * 200`, activated above 50 m³/s |

Each component is clipped to `0-100`; the global score is the **maximum
available component**, not a combined risk estimate. Missing components are
excluded, so two scores may use different evidence sets. Product bands are
Stable `0-<31`, Monitoring `31-<61`, Tipping `61-<81` and Critical `81-100`; see
[`mart_city_zone_current_v2.sql`](../transform/models/mart/mart_city_zone_current_v2.sql).
The formulas, maximum aggregation and bands are not calibrated to observed
harms or externally validated.

Heat uses project baselines, not validated climate normals. The expansion
cohort uses 2014-2023 Open-Meteo Archive API data; the original cohort lacks
exact retrieval provenance. See [Static Seeds](3-staging-layer.md#static-seeds-3).

## Evidence by component

| Component | Current evidence | Interpretation limit |
|---|---|---|
| Heat | Product status says “limited backtest”; no reproducible report is pinned | Open-Meteo Archive API labels are gridded source data, not station truth; the score remains uncalibrated |
| Rain | Product status says “insufficient skill”; no reproducible report is pinned | The conclusion is not independently auditable from the repository and does not validate the operational signal |
| Wind | No realized gust label matching the operational gust formula | Forecast rule only; no outcome-validation claim |
| Air quality | No historical observed-AQ label pipeline | Forecast rule only; no outcome-validation claim |
| River | No gauge label; forecast GloFAS grid cell | Rough grid proxy, not verified urban-river monitoring |

Only Heat and Rain have archive-backed realized-label fields; see
[the mart evidence section](4-mart-layer.md#observed-label-limitation-and-required-product-disclaimer).
River resolves a city coordinate to an approximately 5 km GloFAS cell that may
not represent the intended river. See
[`fetch_flood_discharge`](../ingest/fetcher.py) and the
[city-onboarding caveat](2-ingestion-pipeline.md#configuration-the-city-list).

## Snapshot completeness is not guaranteed

The selector chooses the newest run with any raw evidence. No durable
`started`/`complete`/`failed` manifest exists, and
[`stg_operational_run_v2.sql`](../transform/models/stg/stg_operational_run_v2.sql)
allows partial or still-running runs. The score may use only the available
subset even though missingness remains visible.

Therefore, an active run ID or a non-null score does not prove a complete or
successful ingestion. Inspect snapshot age, source flags,
`available_factor_count`, factor status and coverage before use. See
[Delivery and Retry Semantics](2-ingestion-pipeline.md#delivery-and-retry-semantics).

## Time and provenance limits

### Hourly timestamps are not valid UTC instants

Weather and AQ requests return offset-free local clock text, but the legacy
`valid_ts_utc` BigQuery `TIMESTAMP` treats it as UTC. Daily processing mostly
preserves the intended local date; the instant is shifted and cannot support
exact lead-time, cross-zone or DST analysis. See the
[hourly valid-time caveat](2-ingestion-pipeline.md#hourly-valid-time-caveat),
[`fetcher.py`](../ingest/fetcher.py) and [`loader.py`](../ingest/loader.py).

ML preserves same-run feature lineage and requires labels to have later
recorded ingestion times. This controls known mixing/leakage paths; it does
**not** establish exact provider issue, row availability or UTC lead time,
because `ingested_at_utc` is a job-start proxy.

### ERA5 provenance is unverified

The historical request neither pins `models=era5` nor stores the returned
model/version. Existing `open_meteo_era5` and `era5_*` values are legacy
identifiers, not proof of ERA5. Use **Open-Meteo Archive API** until
provenance is captured. See
[ML validation evidence](11-machine-learning-model.md#validation-evidence-and-uncertainty)
and [`fetch_historical_weather`](../ingest/fetcher.py).

## Permitted and prohibited interpretations

Permitted with the limitations visible:

- reproduce and explain the documented heuristic formulas;
- prioritize inspection within one fresh snapshot when factor availability and
  coverage are shown and comparable;
- describe ML data as same-vintage with explicit outcome-leakage controls; and
- report Heat/Rain results only when tied to a named Open-Meteo Archive API
  source, exact dataset/run and reproducible evaluation artifact.

Do not use the current outputs to claim:

- a probability of an event, a physical tipping point, certified risk class,
  emergency condition or safety instruction;
- comparable absolute risk across cities or runs without equivalent source and
  factor coverage;
- a complete successful ingestion merely because a score is present;
- exact UTC validity, provider issue time or exact forecast lead time;
- verified ERA5, station-observed or gauge-observed provenance; or
- validated predictive skill for Wind, Air quality or River.

## Criteria for removing these limitations

| Limitation | Minimum evidence or engineering change required |
|---|---|
| Heuristic score and bands | Define outcomes; justify/learn weights; publish held-out calibration, sensitivity and uncertainty; validate across independent cities/time; version the contract |
| Heat/Rain evidence | Retain exact source/model provenance and use appropriate independent observations for observed-truth claims |
| Wind/AQ/River evidence | Ingest aligned observed outcomes, document station/gauge matching and pass predeclared baseline-relative gates |
| River proxy | Persist a reviewed river/catchment or gauge mapping per city and remove unsupported cells |
| Partial active runs | Persist run states; promote only completed runs after source, city, row-count and dbt-quality gates |
| Timestamp semantics | Store offset-aware local and correct UTC times plus issue/request metadata; migrate data and test DST boundaries |
| ERA5 naming | Pin or persist the returned model/version, backfill where possible and replace ambiguous legacy labels |

Until each row's criterion is met and reviewed, its limitation must remain in
the relevant API, dashboard and documentation copy.
