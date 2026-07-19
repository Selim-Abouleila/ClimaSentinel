# 11. Machine Learning and MLOps

ClimaSentinel trains `ClimaSentinel_HeatRainForecaster` as an **offline
challenger** for realized Heat and Rain risk at Day +1, Day +2 and Day +3. The
operational endpoint currently serves deterministic same-vintage rules for all
five factors. A registered candidate is not production evidence: it must beat
the corresponding rule baseline before it can receive `champion`, and serving
requires a separate reviewed integration decision.

This boundary avoids both training/serving skew and false claims. Training a
five-component model against later forecasts would teach it to reproduce
another forecast, not validate it against reality.

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
          MLflow `ClimaSentinel_HeatRainForecaster` challenger
                                   │
                    baseline-relative quality gates
                                   │
                         ┌─────────┴─────────┐
                         │ pass             │ reject
                         ▼                  ▼
                 champion may move    alias unchanged

mart_ml_serving_features_current
                 │
                 ▼
backend response: Heat/Rain/Wind/AQ/River same-vintage rules
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

## Training, tracking and challenger evaluation

`model/train.py` logs the challenger to DagsHub MLflow under
`ClimaSentinel_HeatRainForecaster`. Every run records:

- Git commit and DVC snapshot hash;
- schema and data-contract versions;
- ordered targets and horizons;
- four-day purge gap and held-out start date;
- Random Forest hyperparameters; and
- aggregate, per-horizon and per-component MAE/R² metrics; and
- matching same-vintage Heat/Rain rule-baseline metrics on the identical held-out
  rows.

`model/promote.py` evaluates only the learned Heat and Rain challenger outputs.
For every component and horizon, the candidate must:

- have finite R² of at least `0`;
- achieve MAE no greater than `95%` of the exact same-vintage rule-baseline MAE,
  meaning at least a 5% improvement;
- stay below Heat's absolute MAE ceilings of `10`, `11` and `12` for Day +1,
  Day +2 and Day +3 respectively; and
- stay below Rain's absolute MAE ceiling of `7` at every horizon.

Aggregate global and per-horizon metrics remain logged for diagnosis but are no
longer hard gates; averaging Heat with Rain previously obscured which component
actually failed. Missing/non-finite metrics, a schema mismatch or an ordered
contract mismatch still fail evaluation. Wind/AQ/River are not model targets.

Before any alias can move, promotion also downloads the exact registered model
version and runs the fitted-pipeline validator against the semantic contract
embedded in the artifact itself. Matching MLflow parameters are therefore not
enough to promote a missing, corrupt or wrongly ordered estimator.

Promotion also requires at least 50 held-out rows, eight held-out origin dates,
50 finite examples per target, at least five non-zero target values and non-zero
target variance. These evidence checks prevent an apparently strong R² from a
tiny or constant evaluation slice.

The staging and production workflows pass the exact candidate version emitted
by training. Only a complete pass assigns the `champion` alias. They invoke
`python -m model.promote --allow-rejected`: this converts only a completed
quality rejection into a successful report so the declared rule-baseline app
can deploy. It never promotes a rejected model. Authentication, registry,
artifact-contract, metadata and unexpected operational failures remain fatal.
The reusable MLOps workflow publishes the DVC object and Git pointer only after
training and registration succeed.

## Operational rule policy

The FastAPI endpoint does not load the latest candidate merely because training
completed. For the requested horizon, it calculates all five rules from one
complete row in `mart_ml_serving_features_current`, marks a factor unavailable
when its source contract is absent, and chooses the total/driver from available
point estimates.

The response identifies `forecast_rules_baseline`, returns
`model_version: null`, declares no deployed model targets, and identifies every
component as `forecast_rule`. Heat is `era5_backtested_limited`; Rain, Wind, AQ
and River are explicit about their different evidence states: Rain is
`era5_backtested_insufficient_skill`, while Wind, AQ and River are
`not_observation_validated` because their observed labels are not ingested.

The deterministic forecast rules are:

```text
Heat = clip((Tmax[D] - monthly_normal) * 5
            + max(0, Tmax[D+1] - Tmax[D]) * 5)
Rain = clip(precipitation_mm[D] * 2)
Wind = clip(max(0, gust_km_h - 40) * 2.5)
AQ   = clip((European_AQI - 40) * 1.67)

River = clip(max(0, (discharge[D+1] - discharge[D]) / discharge[D]) * 200)
        when discharge[D] > 50 m³/s; otherwise 0
```

Heat requires selected-day and next-day same-vintage weather, so Day +3 uses
stored Day +4 context. Rain requires complete selected-day weather. AQ requires
same-horizon presence, 24-hour coverage and completeness. River
always requires the requested day's same-vintage discharge and, when that value
is above 50 m³/s, also requires the next day's value to calculate velocity. Day
+3 therefore uses the stored Day +4 context when activated. Missing required
data is `unavailable`, not zero.

## Validation evidence and uncertainty

The July 2026 snapshot contained only 81 distinct forecast-origin dates. In its
chronological holdout, the Heat rule materially outperformed the first Random
Forest challenger, but this remains limited seasonal evidence rather than a
mature validation claim. The Rain challenger produced negative held-out R² and
also failed to beat the simple Rain rule. Rain is therefore described as
observation-backtested with insufficient skill, not as lacking observations.
Counts and metrics continue to be logged per run as the snapshot grows; product
copy does not freeze a dynamic day count.

Deterministic rules do not provide empirical prediction intervals. Every
component and top-level confidence/interval field is therefore null and every
uncertainty method is `none`.

## Operational commands

From the repository root:

```bash
python -m model.extract_data
dvc add model/data/training_snapshot.csv
python -m model.train
python -m model.promote

# CI/release mode: report an ordinary quality rejection without deploying it
python -m model.promote --allow-rejected
```

For local tests:

```bash
cd backend
pytest tests/ -v
```

Production and staging challenger evaluation requires DagsHub/MLflow
credentials, while extraction and serving require BigQuery access. A rejected
challenger leaves the rule endpoint and `champion` alias unchanged.

## Current limitation

Only Heat and Rain currently have genuine realized labels, and the available
history is not yet sufficient to deploy the tested challenger. Supporting Wind,
AQ and River as learned outputs requires observed gust, historical AQ and
observed river discharge ingestion, corresponding point-in-time label marts,
retraining and baseline-relative outcome gates. Until a challenger passes and a
serving integration is reviewed, all five outputs remain forecast-rule
estimates with the validation scope stated above.
