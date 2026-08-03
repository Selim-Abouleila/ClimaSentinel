# 4. Mart Layer (Gold)

The mart layer is ClimaSentinel's Gold layer. It has two deliberately separate
responsibilities:

1. calculate the operational Tipping Score used by the dashboards; and
2. provide point-in-time-safe forecast features and realized Open-Meteo
   archive/reanalysis labels for machine learning.

Keeping those paths separate is important. A forecast value is information that
was available when a prediction was made. A realized value is an outcome learned
later. Joining the two without preserving that boundary creates target leakage
and unrealistically optimistic validation results.

All models in this layer are deployed to the `mart` BigQuery dataset. The
`dbt_project.yml` default is `table`; operational "current" models and the ML
serving selector override it with `view` where appropriate.

## Operational score marts

The active operational score path is registry-wide: its configured spine keeps
all 20 active cities in the v2 history, current, zone and detail relations even
when a selected ingestion run is missing source data. Such factors remain NULL
and unavailable rather than disappearing or becoming zero. This scope is
independent from the frozen 10-city point-in-time forecast path.

### `mart_city_score_history_v2` (table)

Calculates the forecast-derived Tipping Score for every city and valid date. It
combines five component indicators and takes their maximum as the global score.

Every component is clipped to the `0-100` range before the maximum is taken.

| Component | Operational calculation |
|---|---|
| Heat | `(Tmax - monthly normal) * 5 + max(0, Tmax[D+1] - Tmax[D]) * 5` |
| Wind | `max(0, gust_km_h - 40) * 2.5` |
| Rain | `precipitation_mm * 2` |
| Air quality | `(European_AQI - 40) * 1.67` |
| River | `max(0, (discharge[D+1] - discharge[D]) / discharge[D]) * 200` when discharge is above 50 m³/s |

The operational mart has an explicit missingness contract. Every factor carries
`*_monitored`, `*_available`, `*_status` and `*_coverage` fields. Status is one
of `available`, `unavailable`, or `not_monitored`; only `available` rows have a
numeric factor score. Heat, Wind, Rain and Air Quality require complete hourly
value coverage for their required date(s). Heat and River velocity also require
an exactly consecutive Day `D+1`. The River monitoring flag comes from
`city_signal_monitoring.csv`, which is validated against
`config/cities.csv:river_enabled`.

No missing input is zero-imputed or carried forward. A measured, fully covered
input may still evaluate to the genuine score `0.0`; unavailable input remains
NULL. `global_tipping_score` is the maximum across available factors only. If no
factor is available it is NULL, `global_score_available` is false and the
driver is `Unavailable`. `overall_coverage` is the mean of monitored-factor
coverage values; unmonitored factors are excluded from its denominator.
`operational_ingestion_run_id` and `operational_ingested_at_utc` identify the
selected snapshot throughout history/current/detail, enabling the 36-hour UI
freshness warning. They do not replace a completed-run manifest, which is not
yet implemented; failed or overlapping ingestion remains an operational audit
gap.

This model is appropriate for operational forecast displays. It is **not a
realized-outcome label table**: its inputs can be forecast values. The ML
training path therefore does not treat its component scores as ground truth.

Despite the `history` name, this is a full-refresh table built from the one
exact run selected by `stg_city_signal_input_v2`. It is history by
forecast-valid date, not an immutable record of what the application showed at
each retrieval. A missing selected-run payload is not filled from an older run,
and a later build can replace the table's dates; use the forecast-vintage marts
for as-of analysis.

### `mart_city_score_current_v2` (view)

Selects the highest forecast-derived score for each city across the two UTC
calendar dates `CURRENT_DATE('UTC')` and the following day, then ranks cities
from highest to lowest risk. This is not a rolling 48-hour interval and is not
anchored separately to each city's local date. A scored date always wins over
an unavailable date; exact ties choose the earlier date deterministically.
Rows also expose `current_score_available`, monitored/available factor counts
and `overall_coverage`. Cities without a score rank after scored cities.

### `mart_city_zone_current_v2` (view)

Aggregates current city scores into Stable, Monitoring, Tipping and Critical
operational zones. A separate Unavailable zone contains rows whose available
factor set is empty.

| Zone | Score range | Meaning |
|---|---:|---|
| Stable | 0 to <31 | Lowest legacy score band |
| Monitoring | 31 to <61 | Elevated legacy score band |
| Tipping | 61 to <81 | High legacy score band |
| Critical | 81-100 | Highest legacy score band |
| Unavailable | NULL | No factor had sufficient input coverage |

The labels and thresholds are product-defined operational bands, not calibrated
event probabilities, validated severity classes or response mandates. Their
names must be presented with the Beta/evidence disclaimer rather than as
standalone safety advice.

### `mart_city_score_detail_v2` (view)

Exposes all five nullable component scores, their monitoring/availability/
coverage metadata and raw forecast context for the city detail page. One
`ROW_NUMBER` selection chooses the complete worst-day row, ordered by score
availability, score descending and date ascending. Every returned field
therefore belongs to the same deterministic date, including on a tie.

### Temporary legacy rollback marts

The unsuffixed `mart_city_score_history`, `mart_city_score_current`,
`mart_city_score_detail` and `mart_city_zone_current` relations remain during
the rollout only so the previous application can be restored without a data
rollback. They retain their legacy schema and scoring semantics, including the
old treatment of missing input. The active backend does not read them, and v2
fields such as `*_available`, `*_coverage` and monitored/available aggregate
counts must not be expected on these unsuffixed relations.

## Point-in-time ML marts

The new ML path starts from `stg_city_signal_vintage`. That staging model
preserves every retrieval and prevents weather, air-quality and flood values
from different ingestion runs from being combined.

Every vintage entry model joins `forecast_city_allowlist.csv`, so these marts
remain restricted to Paris, London, Madrid, Berlin, Rome, Amsterdam, Athens,
Warsaw, Lisbon and Stockholm. The 10 dashboard-only additions do not enter
forecast features, realized training examples or current forecast serving.

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

No realized archive/reanalysis outcome is joined into this model, so the SQL
does not itself introduce outcome leakage. It is the shared feature-definition
source for historical training and live serving. Its point-in-time claim still
relies on `ingested_at_utc`, a job-start availability proxy rather than the
provider's model issue time or a per-city request timestamp.

Eligibility currently requires exactly 24 distinct weather timestamps on every
Horizon 0-4 date. If a provider response represents a DST-transition civil day
with 23 or 25 timestamps, that otherwise complete vintage is excluded from
canonical training and serving. This is a known coverage rule, not evidence that
the source day itself was incomplete.

The old `mart_ml_feature_store` remains temporarily for compatibility. Its
date-based `LEAD()` construction does not guarantee that all horizons came from
the same retrieval, so it must not be used for the new point-in-time training
path.

### `mart_city_realized_weather_daily` (table)

**Grain:** one row per `(city_id, valid_date)`.

This is the realized-label boundary. It is built from
`stg_latest_historical_daily`, whose source is lagged Open-Meteo
archive/reanalysis weather, and exposes:

- realized daily temperature and precipitation;
- the city/month temperature normal;
- next-day realized temperature where required for heat velocity;
- realized Heat and Rain scores;
- source ingestion identifiers and timestamps; and
- per-label and combined availability timestamps.

This realized-weather mart can contain all 20 operational cities. Only rows
that later join an allowlisted forecast vintage can enter
`mart_ml_training_examples`, so the training contract remains restricted to the
original 10 forecast cities.

The availability timestamps are essential. The archive/reanalysis outcome is
published after the valid date, so an example can only enter the training set
after its required outcome has actually been ingested.

The current fetch does not request a fixed `models=era5` source or persist a
returned model/version. Existing `era5_*` validation-status values and the
literal `label_source='open_meteo_era5'` are legacy contract labels, not proof
of exact per-row ERA5 provenance.

Because `stg_latest_historical_daily` retains the latest ingestion of a
city/date, these timestamps are conservative latest-retrieval proxies, not the
first time the outcome became available from the provider.

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
forecast retrieved ──────────────► outcome occurs ──────────────► archive label ingested
        features available             target date                    training eligible
```

Raw air-quality and flood forecast features remain nullable and are accompanied
by explicit presence/completeness flags; they are not backward-filled,
forward-filled or zero-imputed. Only the derived `current_tipping_score`
preserves the legacy forecast-vintage rule in which an absent optional factor
contributes zero to that baseline score. The available-only/NULL-safe maximum
described above applies to the operational v2 marts, not this ML feature mart.

### `mart_ml_serving_features_current` (view)

**Grain:** one latest eligible row per `city_id`.

This is a thin selector over `mart_ml_forecast_features_vintage`. It exposes the
same feature definitions used by `mart_ml_training_examples`, but contains no
realized targets. It accepts only a forecast whose origin equals the current
city-local date. When today's complete vintage is unavailable, it returns no row
for that city instead of silently relabelling yesterday's horizons. Selecting
serving features from the same feature mart is what removes the
training/serving feature-definition skew.

The Python integration now uses this contract directly:

1. `model/extract_data.py` snapshots `mart_ml_training_examples` without
   reconstructing labels or filling optional forecast sources;
2. schema-v3 challenger training learns only the six realized Heat/Rain targets
   (two components for each of Day +1, Day +2 and Day +3);
3. the backend queries `mart_ml_serving_features_current` and calculates all
   five operational rules from the requested horizon's raw same-vintage values;
   and
4. challenger metrics are compared with Heat/Rain rule baselines calculated on
   the exact same chronological holdout rows.

The fitted artifact is registered as `ClimaSentinel_HeatRainForecaster`. A
four-day purge separates training and evaluation dates because the Day +3 Heat
label depends on realized Day +4 temperature. This addresses the current
feature-definition and label-lookahead skew without pretending unsupported
labels exist; it does not by itself establish external validity.

Both operational and realized Heat scores depend on
`transform/seeds/city_monthly_normals.csv`. The 240-row seed deliberately has
two provenance cohorts. The original 10 cities' 120 rows predate the checked-in
generator and retain no exact original retrieval metadata, so those values are
preserved rather than claimed as exactly reproducible. The expansion's 120 rows
were generated from the Open-Meteo Historical Weather API for 2014–2023 by
`transform/scripts/generate_city_monthly_normals.py`; the checked-in provenance
manifest records the request contract, returned grid, aggregation policy,
retrieval time and SHA-256 checksums. Open-Meteo Best Match archives can still
be revised, so comparisons across seed changes must identify the Git revision,
cohort and reviewed seed hash.

## Observed-label limitation and required product disclaimer

The current warehouse supports realized archive/reanalysis labels for
**Heat and Rain only**.

| Component | Realized-label field available? | Reason |
|---|---:|---|
| Heat | Yes | Lagged archive daily temperature and next-day temperature are ingested |
| Rain | Yes | Lagged archive daily precipitation is ingested |
| Wind | No | Archive staging has sustained wind, not the gust observation used by the score |
| Air quality | No | No observed historical AQ ingestion is present |
| River | No | The current river source is a forecast, not observed discharge truth |

These archive-backed Heat/Rain fields are realized labels within the project
contract; they are not independently observed or station-validated truth.

Later forecasts, Horizon 0 values, or forecast revisions must not be relabelled
as observations merely to obtain five target columns. Doing so would train the
model to reproduce another forecast and would make validation metrics
misleading.

Until more evidence and the missing observed sources are available, the
three-day forecast page must expose the operational policy honestly.
Recommended user-facing copy:

> Heat uses a same-vintage forecast rule with a limited Open-Meteo
> archive/reanalysis backtest. Rain was backtested against the same realized
> archive/reanalysis source but showed insufficient predictive skill.
> Wind, air-quality and river-risk still lack observed-label validation.

That disclaimer ships on the three-day forecast page. It must remain visible
until each component has sufficient observed evidence and passes
baseline-relative outcome validation.

## Dependency graph

```text
Operational path
stg_city_signal_input_v2
    └──► mart_city_score_history_v2
             ├──► mart_city_score_current_v2 ──► mart_city_zone_current_v2
             └──► mart_city_score_detail_v2

Legacy rollback path (temporary)
stg_city_signal_input ──► unsuffixed mart_city_score_* relations

Point-in-time ML path
stg_city_signal_vintage
    └──► mart_ml_forecast_features_vintage
             ├──► mart_ml_serving_features_current ──► all-rule backend forecast
             └──► mart_ml_training_examples ──► DVC snapshot ──► Heat/Rain challenger
                        ▲
stg_latest_historical_daily
    └──► mart_city_realized_weather_daily
```

## Data-quality contracts

Schema tests in `_mart_models.yml` enforce mandatory keys, timestamps, flags and
realized Heat/Rain targets. Singular tests additionally verify:

- the v2 operational 20-city spine and monitoring-seed contract;
- one coherent selected ingestion run and consistent selected-run raw
  payloads;
- factor availability/coverage/status invariants, measured-zero preservation,
  and a global score equal to the maximum of available factors only;
- deterministic v2 worst-day selection;
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

These checks run only when `dbt test` is invoked. The scheduled Cloud Run
ingestion path runs `dbt seed` and `dbt run` without tests. Source partial
failures and dbt subprocess failures propagate a nonzero job exit; whole-job
retries are disabled because raw writes are append-only. A green scheduled
execution therefore establishes that the models ran, but not that the separate
dbt test contracts passed.

Pull-request CI performs a credential-free `dbt parse`, but it does not connect
to BigQuery or execute `dbt run`/`dbt test`. The staging workflow gates backend
deployment on already-created v2 schemas, configured city coverage, one
coherent selected run and a snapshot age no greater than 36 hours; it does not
build the models or run the singular test suite. The dbt sources also have no
configured ongoing freshness policy. Application CI success, warehouse test
success and post-cutover raw-data freshness must therefore be verified
separately.

## Deployment and approval sequence

For the operational v2 availability contract, use an expand-and-contract
sequence:

1. Run `make deploy` so `dbt seed/run/test` creates the exact-run v2 staging
   and mart relations while the unsuffixed legacy marts and old application
   remain live.
2. Promote to staging and queue the compatibility frontend.
3. While Railway builds it, run the staging readiness gate against v2 schema
   requirements, all 20 configured city IDs, one selected run and a snapshot
   age no greater than 36 hours; then confirm the frontend's exact commit/run
   marker with the bounded release poll.
4. Queue the backend that reads v2, then require its no-cache health proxy to
   report the same exact release ID before running the Paris forecast and
   Stockholm unmonitored-River E2E checks.
5. Keep the unsuffixed relations only for the agreed rollback window; remove
   them in a separately reviewed cleanup after v2 is stable.

For the separate point-in-time ML path:

1. Run the vintage staging models and tests.
2. Build the four ML marts.
3. Run schema and singular mart tests.
4. Inspect row counts, origin-date coverage, missing optional sources and label
   maturity by horizon.
5. Extract and DVC-track a deterministic `mart_ml_training_examples` snapshot.
6. Train and register a schema-v3 `ClimaSentinel_HeatRainForecaster` candidate.
7. Evaluate the exact candidate against the same-vintage rule baselines and move
   `champion` only if every Heat/Rain horizon passes.
8. Queue and verify the compatibility frontend before queueing the backend rule
   policy, then verify the `forecast_rules_baseline` response in staging E2E
   tests even when the challenger is rejected.

This is an approval sequence, not one atomic scheduled workflow. In particular,
the daily ingestion job does not perform the `dbt test` portions of steps 1 and
3; those tests need an explicit deployment or validation run.

The MLOps workflow publishes the DVC object and commits its pointer only after
extraction, contract validation, training and registry logging succeed. Model
promotion remains a separate downstream gate; a registered version that fails
quality thresholds does not receive the `champion` alias. That rejection does
not block deployment of the explicitly declared operational rule policy.

At the current scale these marts intentionally use straightforward full-refresh
tables plus one serving view. Incremental materialization can be introduced when
warehouse volume makes it necessary; it is not required to establish correct
point-in-time semantics.
