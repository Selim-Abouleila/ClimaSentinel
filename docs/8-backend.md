# 8. Backend Architecture

The FastAPI backend is the boundary between BigQuery and the Next.js client.
The operational Day +1/+2/+3 path intentionally serves transparent
same-vintage rules; registered Heat/Rain models remain offline challengers until
they demonstrate value beyond those baselines.

## Technology stack

- FastAPI on Python 3.11;
- Google BigQuery for dbt mart reads;
- scikit-learn and MLflow/DagsHub for offline challenger evaluation;
- Pydantic response models for the rule-baseline forecast contract; and
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

The dashboard endpoints continue to read the operational score marts:

- `GET /health` returns process liveness and uptime;
- `GET /data/current-scores` reads `mart_city_score_current`;
- `GET /data/history-scores` reads `mart_city_score_history`;
- `GET /data/current-zones` reads `mart_city_zone_current`; and
- `GET /data/city/{city_id}/scores` reads `mart_city_score_detail`.

These marts calculate all five factors from operational inputs. They are not the
realized-label source used to validate the forecast model.

Despite legacy “48-hour” wording elsewhere in the product,
`mart_city_score_current` and `mart_city_score_detail` actually select the two
UTC calendar dates `CURRENT_DATE('UTC')` and the following day. This is not a
rolling 48-hour interval. `mart_city_score_history` is also a rebuilt table of
target dates from the currently transformed forecast, not an archive of
successive forecast runs.

`mart_city_score_detail` uses separate `ANY_VALUE(... HAVING MAX ...)`
aggregates. When both dates tie on the global score, BigQuery may select factor
fields from different tied rows; the detail response is not guaranteed to
represent one deterministic date in that case. See
[Mart Layer](4-mart-layer.md#mart_city_score_detail-view).

`GET /data/history-scores` has a known schema mismatch on this branch: the route
orders by `prediction_date`, while `mart_city_score_history` exposes the date
column as `date`. Until the route is corrected, the BigQuery query is expected
to fail with a `500` response.

## Current API exposure and hardening gaps

The current service is suitable for the public demonstration dashboard, not a
hardened multi-tenant API:

- routes have no application-level authentication or authorization;
- `/docs`, `/openapi.json` and `/metrics` are public;
- CORS is hard-coded with `allow_origins=["*"]`,
  `allow_credentials=True`, and unrestricted methods and headers;
- the `limit` parameters on list endpoints have defaults but no lower or upper
  bounds, and there is no rate limiting or response cache in the application;
- each data request can issue a BigQuery query; and
- unexpected forecast failures currently include the underlying exception text
  in the HTTP `500` detail.

Only the forecast endpoint has a Pydantic response model. The operational
current-score, history, zone and city-detail endpoints return BigQuery rows
directly, so callers should not assume those payloads have the same typed
response-model validation as `CityForecastResponse`.

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

Every response component has `method: forecast_rule`:

| Component | Method | Outcome validation | Uncertainty |
|---|---|---|---|
| Heat | `forecast_rule` | Limited same-vintage backtest against realized ERA5 | None |
| Rain | `forecast_rule` | Backtested against realized ERA5; insufficient predictive skill | None |
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
observed-impact baseline and is separate from the legacy operational mart's
two-date maximum. All component and top-level interval fields are null and
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
