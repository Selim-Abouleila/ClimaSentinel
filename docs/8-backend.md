# 8. Backend Architecture

The FastAPI backend is the boundary between BigQuery, the registered forecast
model and the Next.js client. It deliberately keeps the operational score path
separate from the point-in-time machine-learning path.

## Technology stack

- FastAPI on Python 3.11;
- Google BigQuery for dbt mart reads;
- scikit-learn and MLflow/DagsHub for registered-model inference;
- Pydantic response models for the hybrid forecast contract; and
- Docker and Railway for deployment.

## Application components

| Module | Responsibility |
|---|---|
| `backend/app/main.py` | Routes, BigQuery orchestration, model loading/caching and hybrid response assembly |
| `backend/app/db.py` | Authenticated BigQuery client creation |
| `backend/app/config.py` | Environment-based application, BigQuery and MLflow settings |
| `backend/app/ml_pipeline.py` | Shared schema-v3 preprocessing, target ordering, horizon slicing, purge rules and artifact validation |
| `backend/app/forecast_rules.py` | Pure same-vintage Wind, AQ and River forecast rules |
| `backend/app/schemas.py` | Typed API contract, including availability, method, validation and uncertainty provenance |

## Operational endpoints

The dashboard endpoints continue to read the operational score marts:

- `GET /health` returns service health and uptime;
- `GET /data/current-scores` reads `mart_city_score_current`;
- `GET /data/history-scores` reads `mart_city_score_history`;
- `GET /data/current-zones` reads `mart_city_zone_current`; and
- `GET /data/city/{city_id}/scores` reads `mart_city_score_detail`.

These marts calculate all five factors from operational inputs. They are not the
realized-label source used to validate the forecast model.

## Hybrid Day +1/+2/+3 forecast

`GET /data/city/{city_id}/forecast?horizon_days=1|2|3` reads one row from
`mart_ml_serving_features_current`. That view is produced from the same
point-in-time feature mart as training and returns no row rather than silently
relabeling an old forecast as today's vintage.

The response has two different component methods:

| Component | Method | Outcome validation | Uncertainty |
|---|---|---|---|
| Heat | `learned_model` | Realized ERA5 label | Uncalibrated Random-Forest tree spread |
| Rain | `learned_model` | Realized ERA5 label | Uncalibrated Random-Forest tree spread |
| Wind | `forecast_rule` | No observed gust label yet | None |
| Air quality | `forecast_rule` | No observed AQ label yet | None |
| River | `forecast_rule` | No observed discharge label yet | None |

Wind, AQ and River rules consume only raw values from the same forecast
vintage. River consumes next-day discharge when the requested day's discharge
is above its 50 m³/s activation threshold; River Day +3 therefore uses Day +4
in that case. Optional source gaps are returned as
`available: false`, `estimated_score: null` with an `unavailable_reason`; they
are never represented as zero risk. A genuine zero is returned only when the
required source data is present and the rule evaluates to zero.

The total and primary driver are calculated from available component point
estimates. Top-level uncertainty is populated only when the primary driver is a
learned Heat or Rain output. A rule-driven total has null interval fields,
because deterministic forecast rules do not acquire statistical confidence
merely by being combined with a model.

## Registered-model safety

The learned artifact is registered as `ClimaSentinel_HeatRainForecaster`. An
explicit `MLFLOW_MODEL_VERSION` takes precedence; otherwise the backend resolves
`MLFLOW_MODEL_ALIAS` (default `champion`) to one concrete version and caches that
artifact in memory.

Before prediction, the backend verifies the embedded contract:

- feature schema version `3`;
- exact ordered input columns and city categories;
- target schema `realized_heat_rain_v1`;
- exact six-output Heat/Rain order for Day +1/+2/+3; and
- a fitted two-output-per-horizon Random Forest pipeline.

Old 15-output `ClimaSentinel_RiskForecaster` artifacts are intentionally
incompatible. In staging and production, registry loading, contract validation
or inference failure returns HTTP 503 rather than silently claiming an
unidentified model result. Any development fallback is explicitly identified
in component and response provenance.

## Containerization

`backend/Dockerfile` builds from `python:3.11-slim`, installs
`backend/requirements.txt` and starts Uvicorn. Runtime credentials and model
selection are injected as environment variables; neither service-account keys
nor registry tokens are baked into the image.
