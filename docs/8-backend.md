# 8. Backend Architecture

The FastAPI backend is the boundary between BigQuery and the Next.js client.
The operational Day +1/+2/+3 path intentionally serves transparent
same-vintage rules; registered Heat/Rain models remain offline challengers until
they demonstrate value beyond those baselines.

## Technology stack

- FastAPI on Python 3.11;
- Google BigQuery for dbt mart reads;
- scikit-learn and MLflow/DagsHub for offline challenger evaluation;
- Pydantic response models for operational availability and the rule-baseline
  forecast contract; and
- Docker and Railway for deployment.

## Application components

| Module | Responsibility |
|---|---|
| `backend/app/main.py` | Routes, BigQuery orchestration and rule-baseline response assembly |
| `backend/app/db.py` | Authenticated BigQuery client creation |
| `backend/app/config.py` | Environment-based application and BigQuery settings |
| `backend/app/ml_pipeline.py` | Shared schema-v3 preprocessing, target ordering, horizon slicing, purge rules and artifact validation |
| `backend/app/forecast_rules.py` | Pure same-vintage Heat, Rain, Wind, AQ and River forecast rules |
| `backend/app/schemas.py` | Typed API contract, including availability, method, validation and uncertainty provenance |

## Operational endpoints

The dashboard endpoints read the availability-aware operational v2 marts:

- `GET /health` returns process liveness and uptime;
- `GET /data/current-scores` reads `mart_city_score_current_v2`;
- `GET /data/history-scores` reads `mart_city_score_history_v2`;
- `GET /data/current-zones` reads `mart_city_zone_current_v2`; and
- `GET /data/city/{city_id}/scores` reads `mart_city_score_detail_v2`.

These marts calculate up to five factors from operational inputs. They are not
the realized-label source used to validate the forecast model. A factor score
is nullable and accompanied by `status`, `monitored`, `available`, and
`coverage` fields. Missing AQ or River input therefore crosses the API as NULL,
never as a synthetic green zero.

After a complete ingestion/dbt refresh, the current-score and city-detail
routes can expose all 20 active operational cities. `GET /data/current-scores`
defaults to a bounded limit of 100 so the expanded registry is not truncated by
the former 10-city assumption. The warehouse v2 spine preserves all 20
configured cities even when a source payload is absent; the API itself does not
synthesize cities, factors or scores.

Despite legacy “48-hour” wording elsewhere in the product,
`mart_city_score_current_v2` and `mart_city_score_detail_v2` actually select the two
UTC calendar dates `CURRENT_DATE('UTC')` and the following day. This is not a
rolling 48-hour interval. `mart_city_score_history_v2` is also a rebuilt table of
target dates from the currently transformed forecast, not an archive of
successive forecast runs.

The global/current score is the maximum only across available factors. It can
itself be NULL when no factor is available. The overview payload exposes
`current_score_available`, monitored/available factor counts and
`overall_coverage`; unavailable cities sort after scored cities. Detail rows
are selected as one deterministic complete row, so tied dates can no longer
mix fields. See [Mart Layer](4-mart-layer.md#mart_city_score_detail_v2-view).

Current, history and detail payloads also expose
`operational_ingestion_run_id` and `operational_ingested_at_utc`. They identify
the exact selected snapshot and let the client display its age; they are not a
durable run audit. The ingestion pipeline does not yet persist a completed-run
manifest, so a totally failed run can leave the prior snapshot selected and an
overlapping/in-progress run can briefly become newest. The frontend's
36-hour stale-snapshot banner mitigates this visibility gap, but a committed
run manifest/readiness state remains future hardening.

The unsuffixed operational relations remain temporary legacy rollback
compatibility. They keep their legacy schemas and are not queried by these v2
routes.

## Current API exposure and hardening gaps

The current service is suitable for the public demonstration dashboard, not a
hardened multi-tenant API:

- routes have no application-level authentication or authorization;
- `/docs`, `/openapi.json` and `/metrics` are public;
- CORS is hard-coded with `allow_origins=["*"]`,
  `allow_credentials=True`, and unrestricted methods and headers;
- `/data/current-scores` bounds `limit` to 1–100, while the history and zone
  list limits remain unbounded; there is no rate limiting or response cache in
  the application;
- each data request can issue a BigQuery query; and
- unexpected forecast failures currently include the underlying exception text
  in the HTTP `500` detail.

Current-score, history and city-detail endpoints now have Pydantic response
models. They validate score bounds and reject contradictory combinations such
as `status=not_monitored` with a numeric score, or `status=unavailable` without
monitoring/coverage metadata. The zone endpoint still returns BigQuery rows
directly.

`GET /health` is a liveness check only. It always reports the running process as
healthy and does not test BigQuery credentials, dataset availability, the
serving mart, DagsHub or MLflow. It must not be used as a dependency-readiness
guarantee.

## Rule-baseline Day +1/+2/+3 forecast

`GET /data/city/{city_id}/forecast?horizon_days=1|2|3` reads one row from
`mart_ml_serving_features_current`. That view is produced from the same
point-in-time feature mart as training and returns no row rather than silently
relabeling an old forecast as today's vintage. The query also resolves the
city's temperature normal for the requested **target date month**, avoiding an
origin-month error when a horizon crosses a month boundary.

Forecast serving remains restricted to the original 10 IDs in
`forecast_city_allowlist.csv`. Vienna, Brussels, Copenhagen, Dublin, Oslo,
Helsinki, Prague, Budapest, Zurich and Bucharest can have operational score
responses but have no eligible forecast-serving row and normally return `404`
from this endpoint. The shared `{city_id}` route shape does not imply identical
city scope across operational and forecast endpoints.

Every response component has `method: forecast_rule`:

| Component | Method | Outcome validation | Uncertainty |
|---|---|---|---|
| Heat | `forecast_rule` | Limited same-vintage backtest against realized archive/reanalysis labels | None |
| Rain | `forecast_rule` | Backtested against realized archive/reanalysis labels; insufficient predictive skill | None |
| Wind | `forecast_rule` | No observed gust label yet | None |
| Air quality | `forecast_rule` | No observed AQ label yet | None |
| River | `forecast_rule` | No observed discharge label yet | None |

All rules consume only raw values from the same forecast vintage. Heat uses the
selected day's maximum-temperature departure from its monthly normal plus only
positive next-day temperature velocity. Rain uses selected-day precipitation.
River consumes next-day discharge when the requested day's discharge
is above its 50 m³/s activation threshold. Heat Day +3 always requires the
same-vintage Day +4 temperature; River Day +3 also requires Day +4 discharge
when the Day +3 discharge exceeds the threshold. Optional source gaps are
returned as
`available: false`, `estimated_score: null` with an `unavailable_reason`; they
are never represented as zero risk. A genuine zero is returned only when the
required source data is present and the rule evaluates to zero.

The total and primary driver are calculated from available component point
estimates. Specifically, `estimated_total_tipping_score` is the **maximum**
available component score, not a sum or average, and the primary driver is the
component that supplies that maximum. The `current_tipping_score` comparison
is calculated from the forecast origin day's same-vintage inputs; it is not an
observed-impact baseline and is separate from the operational v2 current
mart's two-date maximum. All component and top-level interval fields are null and
`uncertainty_method` is `none`; deterministic formulas do not create model
confidence intervals.

## Offline challenger boundary

Heat/Rain challengers are registered as `ClimaSentinel_HeatRainForecaster` and
evaluated by `model/promote.py`. Registration or even a `champion` alias does not
silently change the forecast endpoint: serving remains the declared
`forecast_rules_baseline` policy until a separately reviewed release integrates
an eligible challenger.

Before a challenger can be promoted, the MLOps path verifies its embedded
contract:

- feature schema version `3`;
- exact ordered input columns and city categories;
- target schema `realized_heat_rain_v1`;
- exact six-output Heat/Rain order for Day +1/+2/+3; and
- a fitted two-output-per-horizon Random Forest pipeline.

Old 15-output `ClimaSentinel_RiskForecaster` artifacts are intentionally
incompatible. Registry or challenger-evaluation failure cannot alter the rule
response. Missing or incomplete required serving features still produce an
honest 404/availability response rather than an unidentified prediction.

## Containerization

`backend/Dockerfile` builds from `python:3.11-slim`, installs
`backend/requirements.txt` and starts Uvicorn. Runtime BigQuery credentials and
dataset names are injected as environment variables; service-account keys are
never baked into the image. MLflow candidate selection belongs to the separate
training/evaluation workflow and is not consulted by request-time serving.
