# 11. Machine Learning and MLOps

ClimaSentinel's registered forecast model is
`ClimaSentinel_HeatRainForecaster`. It predicts realized Heat and Rain risk for
Day +1, Day +2 and Day +3. Wind, Air Quality and River remain deterministic
same-vintage forecast indicators until genuine observed labels are ingested.

This is an intentional hybrid boundary. Training a five-component model against
later forecasts would teach it to reproduce another forecast, not validate it
against reality.

## End-to-end architecture

```text
forecast vintages                         realized ERA5 weather
        │                                          │
        ▼                                          ▼
mart_ml_forecast_features_vintage     mart_city_realized_weather_daily
        │                                          │
        ├──► mart_ml_serving_features_current      │
        │                                          │
        └──────────────► mart_ml_training_examples ◄┘
                                   │
                                   ▼
                         DVC training snapshot
                                   │
                                   ▼
                   schema-v3 multi-output Random Forest
                                   │
                                   ▼
          MLflow `ClimaSentinel_HeatRainForecaster` candidate
                                   │
                         quality gates + champion
                                   │
                                   ▼
       backend hybrid response: learned Heat/Rain + Wind/AQ/River rules
```

## Point-in-time training data

`model/extract_data.py` reads `mart_ml_training_examples`. Each row is one
canonical `(city_id, forecast_origin_date)` example with:

- a complete weather feature window from one ingestion run;
- the same ordered feature names used by
  `mart_ml_serving_features_current`;
- exact Day +1, Day +2 and Day +3 target dates;
- six mature realized targets: Heat and Rain for each horizon; and
- feature and label run/timestamp provenance.

Labels are built only from `mart_city_realized_weather_daily`, backed by ERA5
historical weather. A label is eligible only after its outcome has occurred and
the corresponding reanalysis has been ingested. Air-quality and flood forecast
features remain nullable; their upstream mart also retains explicit source
presence/completeness flags for rule-serving decisions. Extraction does not
forward-fill, backward-fill or replace a missing optional source with zero.

The realized score definitions are clipped to `0-100`:

```text
Heat(D) = (Tmax(D) - monthly_normal) * 5
          + max(0, Tmax(D+1) - Tmax(D)) * 5

Rain(D) = precipitation_mm(D) * 2
```

Because the Day +3 Heat target depends on realized Day +4 temperature, the
chronological evaluation split purges the four dates immediately before the
held-out test window. Splitting is performed on complete origin dates, not on
random city rows.

## Schema-v3 model contract

The shared contract lives in `backend/app/ml_pipeline.py`. Training and serving
both call the same preprocessing and feature-order functions.

The six ordered outputs are:

```text
future_heat_score_1d, future_rain_score_1d,
future_heat_score_2d, future_rain_score_2d,
future_heat_score_3d, future_rain_score_3d
```

Each horizon therefore selects a two-output block; Day +1 and Day +2 are genuine
fitted outputs rather than copies of Day +3.

The pipeline contains:

1. a `ColumnTransformer` that median-imputes numeric model inputs, adds missing
   indicators, and one-hot encodes the fixed monitored-city vocabulary; and
2. a `MultiOutputRegressor(RandomForestRegressor)` with one fitted forest for
   each ordered target.

Imputation statistics are fitted on the training partition only. The raw row is
retained separately for Wind/AQ/River rules, so an imputed model value can never
masquerade as an available operational source.

The serialized artifact embeds and validates:

- `feature_schema_version = 3`;
- `target_schema_version = realized_heat_rain_v1`;
- `training_data_contract = mart_ml_training_examples_v1`;
- horizons `(1, 2, 3)`;
- exact ordered feature and target columns; and
- learned component order `(heat, rain)`.

Shape alone is insufficient: a six-output artifact with the wrong semantic
order is rejected. Legacy 15-output `ClimaSentinel_RiskForecaster` artifacts are
also rejected rather than partially sliced.

## Training, tracking and promotion

`model/train.py` logs the candidate to DagsHub MLflow under
`ClimaSentinel_HeatRainForecaster`. Every run records:

- Git commit and DVC snapshot hash;
- schema and data-contract versions;
- ordered targets and horizons;
- four-day purge gap and held-out start date;
- Random Forest hyperparameters; and
- aggregate, per-horizon and per-component MAE/R² metrics.

`model/promote.py` evaluates only the learned Heat and Rain outputs. The current
gates require R² of at least `0.35`; horizon MAE must be at most `7`, Heat's
component MAE at most `10`, and Rain's component MAE at most `7`. Missing or
non-finite required metrics, a schema mismatch or an ordered-contract mismatch
fails promotion. Wind/AQ/River rules are not model targets and cannot pass or
fail learned-model quality gates.

Promotion also requires at least 50 held-out rows, eight held-out origin dates,
50 finite examples per target, at least five non-zero target values and non-zero
target variance. These evidence checks prevent an apparently strong R² from a
tiny or constant evaluation slice.

The staging and production workflows pass the exact candidate version emitted
by training. Only after it passes does promotion assign the `champion` alias.
The reusable MLOps workflow publishes the DVC object and Git pointer only after
training and registration succeed.

## Serving and model selection

The FastAPI endpoint loads one concrete model version. An explicit
`MLFLOW_MODEL_VERSION` overrides `MLFLOW_MODEL_ALIAS`; otherwise the alias
defaults to `champion`. The resolved version is validated and cached in memory.
Responses expose that concrete `model_version` and the feature-vintage run and
timestamp.

For the requested horizon, the backend:

1. obtains the matching two learned Heat/Rain values and tree spreads;
2. calculates Wind, AQ and River from raw same-vintage forecast inputs;
3. marks a rule factor unavailable when its required source coverage is absent;
4. chooses total and driver from available estimates; and
5. returns explicit method, validation and uncertainty provenance per factor.

The deterministic forecast rules are:

```text
Wind = clip(max(0, gust_km_h - 40) * 2.5)
AQ   = clip((European_AQI - 40) * 1.67)

River = clip(max(0, (discharge[D+1] - discharge[D]) / discharge[D]) * 200)
        when discharge[D] > 50 m³/s; otherwise 0
```

AQ requires same-horizon presence, 24-hour coverage and completeness. River
always requires the requested day's same-vintage discharge and, when that value
is above 50 m³/s, also requires the next day's value to calculate velocity. Day
+3 therefore uses the stored Day +4 context when activated. Missing required
data is `unavailable`, not zero.

## Tree-spread uncertainty

For each learned output, the backend calculates the standard deviation of the
individual tree predictions and displays:

```text
margin = 1.96 × tree_standard_deviation
lower  = clip(point_estimate - margin)
upper  = clip(point_estimate + margin)
```

Random Forest trees are correlated and this interval has not been calibrated
against held-out empirical coverage. It is therefore an **uncalibrated
tree-spread indicator**, not a guaranteed 95% confidence or prediction interval.
Wind, AQ and River rules have no model interval. Top-level interval fields are
null when a rule-derived factor is the primary driver.

## Operational commands

From the repository root:

```bash
python -m model.extract_data
dvc add model/data/training_snapshot.csv
python -m model.train
python -m model.promote
```

For local tests:

```bash
cd backend
pytest tests/ -v
```

Production and staging require DagsHub/MLflow credentials and BigQuery access.
Registry selection, contract validation or prediction failure returns HTTP 503
instead of an unidentified production fallback.

## Current limitation

Model validation covers Heat and Rain only. Supporting all five factors as
learned outputs requires observed gust, historical AQ and observed river
discharge ingestion, corresponding point-in-time label marts, retraining and
outcome-based promotion thresholds. Until then, documentation and the forecast
page must continue to identify Wind, AQ and River as forecast-rule estimates.
