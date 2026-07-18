# 4. Mart Layer (Gold)

The mart layer is ClimaSentinel's Gold layer. It has two deliberately separate
responsibilities:

1. calculate the operational Tipping Score used by the dashboards; and
2. provide point-in-time-safe forecast features and realized ERA5 reanalysis
   labels for machine learning.

Keeping those paths separate is important. A forecast value is information that
was available when a prediction was made. A realized value is an outcome learned
later. Joining the two without preserving that boundary creates target leakage
and unrealistically optimistic validation results.

All models in this layer are deployed to the `mart` BigQuery dataset. The
`dbt_project.yml` default is `table`; operational "current" models and the ML
serving selector override it with `view` where appropriate.

## Operational score marts

### `mart_city_score_history` (table)

Calculates the forecast-derived Tipping Score for every city and valid date. It
combines five component indicators and takes their maximum as the global score.

Every component is clipped to the `0-100` range before the maximum is taken.

| Component | Operational calculation |
|---|---|
| Heat | `(Tmax - monthly normal) * 5 + max(0, Tmax[D+1] - Tmax[D]) * 5` |
| Wind | `max(0, gust_km_h - 40) * 2.5` |
| Rain | `precipitation_mm * 2` |
| Air quality | `(European_AQI - 40) * 1.67`, with legacy prior-value fallback |
| River | `max(0, (discharge[D+1] - discharge[D]) / discharge[D]) * 200` when discharge is above 50 m³/s |

This model is appropriate for operational forecast displays. It is **not an
realized-outcome label table**: its inputs can be forecast values. The ML
training path therefore does not treat its component scores as ground truth.

### `mart_city_score_current` (view)

Selects the highest forecast-derived score for each city in the current 48-hour
window and ranks cities from highest to lowest risk.

### `mart_city_zone_current` (view)

Aggregates current city scores into Stable, Monitoring, Tipping and Critical
operational zones.

| Zone | Score range | Meaning |
|---|---:|---|
| Stable | 0 to <31 | Signals remain within the normal operating range |
| Monitoring | 31 to <61 | Elevated signals require observation |
| Tipping | 61 to <81 | Rapidly rising tension requires preparation |
| Critical | 81-100 | Severe operational risk requires immediate attention |

### `mart_city_score_detail` (view)

Exposes the five component scores and their raw forecast context for the city
detail page. It selects one internally consistent worst-day row per city.

## Point-in-time ML marts

The new ML path starts from `stg_city_signal_vintage`. That staging model
preserves every retrieval and prevents weather, air-quality and flood values
from different ingestion runs from being combined.

### `mart_ml_forecast_features_vintage` (table)

**Grain:** one row per
`(ingestion_run_id, city_id, forecast_origin_date)`.

This model pivots one exact forecast vintage into a wide feature vector. All
weather, air-quality and flood values on a row come from the same ingestion run.
It contains:

- origin and ingestion provenance;
- Horizon 0 context;
- forecast values for Day +1, Day +2 and Day +3;
- Day +4 temperature and river context needed to evaluate Day +3 velocity-based
  scores without crossing forecast vintages;
- expected-date, source-presence and daily-coverage flags; and
- deterministic eligibility and canonical-vintage indicators.

No realized ERA5 outcome is joined into this model. It is therefore safe to use
as the shared source for both historical training features and live serving
features.

The old `mart_ml_feature_store` remains temporarily for compatibility. Its
date-based `LEAD()` construction does not guarantee that all horizons came from
the same retrieval, so it must not be used for the new point-in-time training
path.

### `mart_city_realized_weather_daily` (table)

**Grain:** one row per `(city_id, valid_date)`.

This is the realized-label boundary. It is built from
`stg_latest_historical_daily`, whose source is Open-Meteo ERA5 historical
weather, and exposes:

- realized daily temperature and precipitation;
- the city/month temperature normal;
- next-day realized temperature where required for heat velocity;
- realized Heat and Rain scores;
- source ingestion identifiers and timestamps; and
- per-label and combined availability timestamps.

The availability timestamps are essential. ERA5 is published after the valid
date, so an example can only enter the training set after its required outcome
has actually been ingested.

This mart does not manufacture labels for unsupported components. Sustained
wind is retained as realized reanalysis context, but it cannot reproduce the
operational gust-based Wind score.

### `mart_ml_training_examples` (table)

**Grain:** one row per `(city_id, forecast_origin_date)`.

This model selects one eligible forecast vintage per city and local origin date,
then joins it to mature realized labels for Day +1, Day +2 and Day +3. The
latest eligible complete vintage is selected deterministically for each city and
local origin date so manual retries do not multiply near-identical examples.

The output contains the exact wide feature contract used by serving plus:

- `target_date_1d`, `target_date_2d` and `target_date_3d`;
- realized `future_heat_score_*` targets;
- realized `future_rain_score_*` targets; and
- label source, run and availability provenance.

Rows are retained only when the complete weather feature window is available,
all three Heat and Rain label dates are mature, and every label was ingested
after the forecast vintage. This enforces the direction of time:

```text
forecast retrieved ──────────────► outcome occurs ──────────────► ERA5 label ingested
        features available             target date                    training eligible
```

Raw air-quality and flood forecast features remain nullable and are accompanied
by explicit presence/completeness flags; they are not backward-filled,
forward-filled or zero-imputed. Only the derived `current_tipping_score`
preserves the legacy operational rule in which an absent optional factor
contributes zero to that baseline score.

### `mart_ml_serving_features_current` (view)

**Grain:** one latest eligible row per `city_id`.

This is a thin selector over `mart_ml_forecast_features_vintage`. It exposes the
same feature definitions used by `mart_ml_training_examples`, but contains no
realized targets. It accepts only a forecast whose origin equals the current
city-local date. When today's complete vintage is unavailable, it returns no row
for that city instead of silently relabelling yesterday's horizons. Selecting
serving features from the same feature mart is what removes the
training/serving feature-definition skew.

The current Python extractor and backend are not switched by this dbt-only
change. After the marts have been run and their output has been approved, a
separate integration change must:

1. extract the versioned training snapshot from `mart_ml_training_examples`;
2. train only against its realized Heat and Rain targets;
3. query `mart_ml_serving_features_current` in the forecast endpoint; and
4. verify the Python feature names and ordering against the dbt serving contract.

## Observed-label limitation and required product disclaimer

The current warehouse supports honest realized ERA5 reanalysis labels for
**Heat and Rain only**.

| Component | Observed label currently available? | Reason |
|---|---:|---|
| Heat | Yes | ERA5 daily temperature and next-day temperature are ingested |
| Rain | Yes | ERA5 daily precipitation is ingested |
| Wind | No | ERA5 staging has sustained wind, not the gust observation used by the score |
| Air quality | No | No observed historical AQ ingestion is present |
| River | No | The current river source is a forecast, not observed discharge truth |

Later forecasts, Horizon 0 values, or forecast revisions must not be relabelled
as observations merely to obtain five target columns. Doing so would train the
model to reproduce another forecast and would make validation metrics
misleading.

Until observed gust, AQ and river-discharge sources are ingested, the three-day
forecast page must distinguish validated model outputs from forecast/rule-based
indicators. Recommended user-facing copy:

> Model validation currently covers heat and rainfall only. Wind, air-quality
> and river-risk values are forecast-based indicators and are not yet validated
> against observed outcomes.

That disclaimer ships on the three-day forecast page with this change. It must
remain visible until observed Wind, Air Quality and River labels are ingested
and those components have passed outcome-based validation.

## Dependency graph

```text
Operational path
stg_city_signal_input
    └──► mart_city_score_history
             ├──► mart_city_score_current ──► mart_city_zone_current
             └──► mart_city_score_detail

Point-in-time ML path
stg_city_signal_vintage
    └──► mart_ml_forecast_features_vintage
             ├──► mart_ml_serving_features_current ──► backend (next change)
             └──► mart_ml_training_examples ──► DVC snapshot (next change)
                        ▲
stg_latest_historical_daily
    └──► mart_city_realized_weather_daily
```

## Data-quality contracts

Schema tests in `_mart_models.yml` enforce mandatory keys, timestamps, flags and
realized Heat/Rain targets. Singular tests additionally verify:

- the declared grain of every new mart;
- reverse coverage from every eligible source row into its expected mart;
- exact Day +1/Day +2/Day +3/Day +4 calendar alignment within a forecast row;
- same-vintage feature payload/flag lineage and complete required weather
  windows;
- at most one current-local-date serving row per city and eligibility of that
  source vintage;
- exact target-date alignment in training examples; and
- temporal safety: label availability must be later than feature ingestion.

The vintage staging tests remain part of the dependency contract. A mart test
passing cannot compensate for a failed same-vintage staging lineage test.

## Deployment and approval sequence

1. Run the vintage staging models and tests.
2. Build the four new ML marts.
3. Run schema and singular mart tests.
4. Inspect row counts, origin-date coverage, missing optional sources and label
   maturity by horizon.
5. Approve a deterministic `mart_ml_training_examples` snapshot.
6. Only then switch the extractor, training pipeline and backend serving query.

At the current scale these marts intentionally use straightforward full-refresh
tables plus one serving view. Incremental materialization can be introduced when
warehouse volume makes it necessary; it is not required to establish correct
point-in-time semantics.
