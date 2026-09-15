# 4. Mart Layer (Gold)

The mart layer is ClimaSentinel's Gold layer. It has two deliberately separate
responsibilities:

1. calculate the operational Tipping Score used by the dashboards; and
2. provide same-vintage forecast features with explicit outcome-leakage
   controls and realized Open-Meteo Archive API labels for machine
   learning.

Before interpreting any score, zone, label or forecast metric, read the
governing [critical interpretation and evidence limits](0-critical-limitations.md).
The Tipping Score is an uncalibrated Beta prioritization heuristic, not a
probability, physical tipping-point model, validated severity class or safety
recommendation.

Keeping those paths separate is important. The current evaluation contract
groups forecast features from one retrieval run and requires the realized label
to have a later recorded ingestion time. Joining forecast and realized data
without that boundary creates target leakage and unrealistically optimistic
validation results. Recorded ingestion times remain proxies with the limits
described in Doc 0.

All models in this layer are deployed to the `mart` BigQuery dataset. The
`dbt_project.yml` default is `table`; operational "current" models and the ML
serving selector override it with `view` where appropriate.

## Operational score marts

The active operational score path is registry-wide: its configured spine keeps
all 20 active cities in the v2 history, current, zone and detail relations even
when a selected ingestion run is missing source data. Such factors remain NULL
and unavailable rather than disappearing or becoming zero. This scope is
independent from the frozen 10-city same-vintage ML path.

### `mart_city_score_history_v2` (table)

Calculates the forecast-derived Tipping Score for every city and valid date. It
combines five component indicators by default and takes their maximum as the
global score.
It also calculates Cold independently in the history table, with its own
monitoring and availability fields. Six-factor aggregation is implemented behind
`cold_in_global_score: false`, pending isolated staging verification and a
coordinated application/data release.

These formulas, multipliers, activation thresholds and the maximum aggregation
are product-defined and uncalibrated. Their permitted uses and evidence gaps are
defined in [Doc 0](0-critical-limitations.md#status-of-the-tipping-score).

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

#### Cold-temperature diagnostic

The history mart exposes three additional columns for inspecting cold conditions:

| Column | Meaning |
|---|---|
| `temperature_2m_min` | Daily minimum forecast temperature from the selected operational run, in °C. |
| `normal_temperature_2m_min` | Seeded 2014–2023 average daily minimum for the same city and calendar month, in °C. |
| `cold_anomaly_c` | `ROUND(GREATEST(0, normal_temperature_2m_min - temperature_2m_min), 2)`, in °C below normal. |

The anomaly requires 24 non-null hourly temperature readings and a finite daily
minimum and baseline. Missing, incomplete or non-finite inputs produce NULL.
At or above normal produces zero; an actual 0°C temperature remains valid input.
For example, a normal minimum of 2.3°C and a forecast minimum of −5°C produce
7.3°C below normal. Only the current day is required, so the last complete
forecast day can have a cold anomaly even when Heat lacks its next-day input.

This diagnostic uses the existing operational date and city/month join. The
staging date is derived from `DATE(valid_ts_utc)`, while the seed averages
city-local calendar days. This addition preserves that existing date convention.

The anomaly is not a 0–100 risk score. It does not enter the global score,
primary driver, factor counts or coverage aggregates. Inspect it in
`mart.mart_city_score_history_v2` or on the selected date in
`mart.mart_city_score_detail_v2`. The history/detail APIs expose the Cold fields;
the ML and three-day forecast contracts still omit Cold.

After updating the GCP checkout, run `make dbt-run` and `make dbt-test`.
The cold-anomaly fixture unit test covers anomaly and Cold-score boundaries,
missingness, city/month selection and unchanged five-factor outputs. The
singular test `assert_city_cold_anomaly_contract` checks diagnostic lineage and
availability on built data. `assert_city_cold_score_contract` checks Cold's
monitoring lineage, eligibility, status, coverage and finite score range.
The unit test uses SQL fixtures to represent NaN and infinity. Its expected
fixture includes every history-model output column, as required by
[dbt's SQL fixture format](https://docs.getdbt.com/reference/resource-properties/data-formats),
including run/source metadata and the existing factor outputs. Keep that
fixture aligned when adding model columns. To rerun only this unit test:

```bash
dbt test --project-dir transform --profiles-dir transform --select test_cold_anomaly_v2
```

#### Cold scoring rule: `cold_anomaly_v1`

**Status:** implemented in `mart_city_score_history_v2`. After applying the
dbt changes, the history table exposes `cold_score`, `cold_status`,
`cold_monitored`, `cold_available` and `cold_coverage`, alongside the raw Tmin,
monthly reference and anomaly. Cold is excluded from the live global score,
driver, factor counts and overall coverage pending coordinated API/UI support.
The detail view passes through these fields from its selected history row;
current/detail aggregates still use five factors by default. Typed API responses
expose Cold independently and validate aggregates using the stored mode.
The rule identifier names this specification, not a warehouse column.

`cold_monitored` comes from `city_signal_monitoring` through
`stg_city_signal_input_v2`, and the city policy requires it true for all 20
active cities. See [the seed and staging contract](3-staging-layer.md#static-seeds-3).

**Meaning:** Cold measures how far the daily forecast minimum falls below this
city's monthly minimum-temperature reference. Absolute Tmin contributes only
through that difference; there is no separate freezing threshold, absolute-cold
bonus, wind-chill term, persistence requirement or next-day velocity term in
this first version. The existing seeded reference and operational date
convention are reused, with the [time limitations in Doc 0](0-critical-limitations.md#time-and-provenance-limits).

For a monitored city with a usable current-day anomaly:

```text
cold_score = ROUND(LEAST(100.0, 5.0 * cold_anomaly_c), 1)
```

The multiplier is **5 score points per degree Celsius below normal**. This
reuses the coefficient of the existing Heat anomaly term as an initial product
choice. It is not fitted to outcomes or evidence that Heat and Cold have equal
impacts. The anomaly-only rule uses the data already available and makes the
first version straightforward to inspect. A different coefficient or an
absolute-temperature term would require a revised rule and reviewed examples.

| Decision | Contract |
|---|---|
| Activation | Apply the formula to a non-null, finite, non-negative `cold_anomaly_c` when `cold_monitored = true`. |
| Zero | An anomaly of zero produces `0.0`, including temperatures at or above the monthly reference. |
| Growth | Linear: a 5°C anomaly gives 25 points; a 10°C anomaly gives 50 points. |
| Saturation | Clipping starts at a 20°C anomaly; larger anomalies stay at `100.0`. Final rounding can also display `100.0` just below that threshold. |
| Rounding | Reuse `cold_anomaly_c` already rounded to two decimals; multiply, cap at 100, then round the score to one decimal. Use decimal arithmetic for this calculation, with halfway values rounding away from zero. |
| Missingness | Missing/incomplete/non-finite inputs produce a NULL score; never substitute zero or an older run. |
| Monitoring | `cold_monitored = false` produces a NULL score. Cold monitoring is independent of `heat_monitored`; the current city policy requires it true for every active city. Missing monitoring configuration is a contract error. |
| Forecast horizon | Require only the current operational date. The last complete forecast day remains eligible without tomorrow's inputs. |

The BigQuery implementation caps the non-negative anomaly at 20°C before
casting it to `NUMERIC` and multiplying by five. This is equivalent to capping
the score at 100 and avoids overflowing the decimal cast for very large finite
anomalies. Decimal arithmetic prevents binary floating-point representation
from deciding a rounding tie. The default [BigQuery `ROUND` mode](https://cloud.google.com/bigquery/docs/reference/standard-sql/mathematical_functions#round)
is used, and the final score is exposed as `FLOAT64`, consistent with the other
factors.

The factor uses the existing availability conventions. Required inputs
are a finite daily Tmin, a finite monthly Tmin reference and exactly 24 non-null
temperature readings from the selected run. The existing count measures
non-null readings; it is not a count of individually finite hourly values.

| Input state | `cold_score` | `cold_status` | `cold_available` | `cold_coverage` |
|---|---|---|---|---|
| Not monitored | NULL | `not_monitored` | false | NULL |
| Monitored, all required inputs usable | Formula above | `available` | true | `1.0` |
| Monitored, finite Tmin/reference, 1–23 non-null readings | NULL | `unavailable` | false | `ROUND(reading_count / 24.0, 3)` |
| Monitored, missing/non-finite Tmin/reference or invalid count (NULL, 0, negative or >24) | NULL | `unavailable` | false | `0.0` |
| Monitored, otherwise usable inputs but invalid anomaly (NULL, non-finite or negative) | NULL | `unavailable` | false | `0.0` |
| Missing monitoring flag (contract error) | NULL | `unavailable` | false | `0.0` |

An invalid anomaly with otherwise usable inputs is also a contract violation;
the contract test must fail for that state. The diagnostic itself stays independent
of monitoring. Missing monitoring configuration also fails the contract tests.

**Worked examples.** These are illustrative inputs, not additional seed values.
Unless noted, Cold is monitored, all inputs are finite and the count is 24.

| Example | Normal Tmin (°C) | Forecast Tmin (°C) | `cold_anomaly_c` | `cold_score` |
|---|---:|---:|---:|---:|
| Below the monthly reference | 2.30 | -5.00 | 7.30 | 36.5 |
| Exactly normal | 4.10 | 4.10 | 0.00 | 0.0 |
| Above normal | 2.30 | 5.00 | 0.00 | 0.0 |
| An actual 0°C minimum | 2.30 | 0.00 | 2.30 | 11.5 |
| Rounding at the final score | 2.30 | 1.07 | 1.23 | 6.2 |
| Rounding to 100 before clipping | 2.30 | -17.69 | 19.99 | 100.0 |
| Exactly at the clipping threshold | 2.30 | -17.70 | 20.00 | 100.0 |
| Beyond saturation | 2.30 | -22.70 | 25.00 | 100.0 |
| Below zero but normal for the month | -10.00 | -10.00 | 0.00 | 0.0 |
| Above zero but colder than normal | 20.00 | 12.00 | 8.00 | 40.0 |
| Incomplete day: 23 readings | 2.30 | -5.00 | NULL | NULL |
| Missing monthly reference | NULL | -5.00 | NULL | NULL |
| NaN or infinite forecast Tmin | 2.30 | non-finite | NULL | NULL |
| Cold not monitored | 2.30 | -5.00 | 7.30 | NULL |

A zero score means no below-reference anomaly at the stored precision; it
does not establish safe absolute conditions. A positive score can occur above
freezing. This is a product-defined Beta anomaly indicator with no Cold
outcome calibration or backtest. It does not implement a standard cold-spell
index: for comparison, the [Climdex CSDI definition](https://climate-scenarios.canada.ca/?page=climdex-indices)
counts days in spells of at least six consecutive days below a daily Tmin
10th-percentile threshold. The monthly mean seed does not supply that percentile.

**Verification:** fixture unit tests cover rounding, clipping, increasing
anomalies, missing and invalid counts, non-finite values, unmonitored Cold,
city/month selection and independence from Heat or tomorrow. The expected SQL
includes all history output columns and verifies the existing five-factor
results even when Cold exceeds their maximum. Schema and singular tests check
Cold metadata, source lineage, eligibility, coverage and finite 0–100 scores.
Run `make dbt-run` followed by `make dbt-test` against BigQuery, then inspect
the new fields directly (replace `PROJECT_ID`):

```sql
SELECT city_id, date, temperature_2m_min, normal_temperature_2m_min,
       cold_anomaly_c, cold_score, cold_status, cold_monitored,
       cold_available, cold_coverage, global_tipping_score
FROM `PROJECT_ID.mart.mart_city_score_history_v2`
ORDER BY city_id, date;
```

Cold is now available in history, the detail view and their API responses. The
city-detail UI displays its score, availability and temperature context from the
selected row. Existing global score, driver, counts and
coverage stay on five factors until the six-factor aggregation change is
released with compatible backend/frontend contracts.
The opt-in aggregation and consumer selection are tested as described below.
ML features, labels and the three-day forecast experience
require their own later Cold specification.

#### Six-factor aggregation activation

`transform/dbt_project.yml` defines the boolean `cold_in_global_score`, default
`false`. With that default, all existing aggregate values and date selection
remain on Heat, Wind, Rain, Air Quality and River. Cold's individual score and
detail fields are available in either mode. Non-boolean values, including the
string `"false"`, cause a compilation error instead of silently enabling Cold.

The history table now persists that mode as a Boolean column also named
`cold_in_global_score`. Current/detail project it from their selected history
row; they do not recompute it from a later dbt invocation. API validators use
this stored mode so both five- and six-factor rows have an explicit contract.
The mode is independent of `cold_monitored` and `cold_available`; a non-river
city can have five monitored factors even when six-factor aggregation is enabled.
Schema tests require the field, and data tests verify configuration and
history/current/detail lineage. Refresh the marts before deploying the new API.

When the setting is `true`, the same history model includes Cold in:

| Output | Six-factor behavior |
|---|---|
| `global_tipping_score` | Maximum non-null score across all six factors; NULL only when all six are unavailable. |
| `primary_driver` | `Unavailable` for NULL, `Stable` for zero; positive ties retain Heat → River/Flood → Wind → Rain → Air Quality → Cold priority. |
| `monitored_factor_count` | Count of all six monitoring flags; unmonitored Cold contributes zero. |
| `available_factor_count` | Count of all six available scores; a valid Cold zero counts as available. |
| `overall_coverage` | Mean unrounded input coverage over monitored factors, rounded to three decimals; partial Cold contributes fractional coverage even though its score is NULL. |

Driver selection uses scores before the existing final display rounding. Two
displayed scores can therefore tie while the slightly larger underlying score
determines the driver. The data test checks driver membership and the displayed
maximum; literal unit cases verify exact positive tie priority. The coverage
data test allows a 0.001 rounding difference when reconstructing the mean from
already rounded per-factor fields.

Current/detail views consume the resulting global score and select the same
complete row by availability, score descending, then earlier date. For example,
today's five-factor maximum 20 with Cold 100 beats tomorrow's maximum 40 with
Cold 10 when enabled; the default still selects tomorrow. A sole available Cold
score, including zero, wins over an unavailable date. Current ranking and zone
membership follow the selected aggregate; zone thresholds are unchanged.

`make dbt-test` exercises both modes through native unit-test variable overrides:
`test_cold_anomaly_v2` verifies the default five-factor contract;
`test_cold_aggregate_v2` verifies six-factor arithmetic and missingness;
`test_cold_aggregate_current_v2` and `test_cold_aggregate_detail_v2` verify
six-factor date selection and ranking using complete SQL fixtures. These tests
use mocked inputs and do not activate six-factor scoring in the built marts.
`assert_city_score_availability_contract` follows the configured aggregate mode;
`assert_city_score_v2_current_detail_consistent` checks matching aggregates,
run provenance and ranking across the built consumer views.

**Release boundary:** backend and frontend code now support both modes, and the
city-detail UI displays Cold independently when the stored mode is false.
Local fixture browser tests cover the visible states; isolated staging and
Cold-specific deployment gates remain required.
Keep this setting false until compatible application versions are deployed and
staging data is isolated. Use PR `dev` → `staging`, deploy and verify both modes
there, and only then open PR `staging` → `main`. Enable the setting in the release's dbt
configuration and rebuild/deploy the ingestion image so scheduled runs retain
the same mode. Run the models and tests with matching configuration and verify
API responses and dashboard behavior together. Changing `--target` alone does
not create an isolated preview: the project uses the same explicit `stg`/`mart`
schemas. The normal `make dbt-run` / `make dbt-test` workflow keeps the default
five-factor live behavior while validating the enabled unit cases. The current
production Railway workflow does not deploy the application; merging `main`
alone is not evidence that compatible production services are running.

### `mart_city_score_current_v2` (view)

Selects the highest forecast-derived score for each city across the two UTC
calendar dates `CURRENT_DATE('UTC')` and the following day, then ranks cities
from highest to lowest operational heuristic score. This is not a rolling
48-hour interval and is not anchored separately to each city's local date. A
scored date always wins over an unavailable date; exact ties choose the earlier
date deterministically.
Rows also expose `current_score_available`, monitored/available factor counts
and `overall_coverage`, plus the stored `cold_in_global_score` mode. Cities
without a score rank after scored cities.

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

Exposes the five aggregate component scores plus the independent Cold score,
their monitoring/availability/coverage metadata and raw forecast context. One
`ROW_NUMBER` selection chooses the complete worst-day row, ordered by score
availability, score descending and date ascending. Every returned field
therefore belongs to the same deterministic date, including on a tie.

The Cold projection adds `cold_score`, `cold_status`, `cold_monitored`,
`cold_available`, `cold_coverage`, `temperature_2m_min`,
`normal_temperature_2m_min` and `cold_anomaly_c`. All eight values come directly
from the row identified by `score_date` and `operational_ingestion_run_id`.
NULL scores, fractional coverage and unmonitored states are preserved.

With the default setting, the chosen date uses the five-factor global score.
A larger Cold score on the other date does not change the selection. For example, if today has
global score 20 and Cold 100, while tomorrow has global score 40 and Cold 10,
detail selects tomorrow and exposes Cold 10. When both dates lack a five-factor
score, the earlier date wins even if Cold is available. Cold does not change
ranking, driver selection, factor counts or overall coverage in that mode.
With `cold_in_global_score: true`, the same selector uses the six-factor
aggregate described above; every projected field still comes from one row.

The backend's explicit SELECT and typed response expose all six factors, Cold
temperature context and the stored aggregation mode. The city-detail UI displays
Cold after Heat, with the forecast Tmin, monthly normal Tmin and anomaly for
`score_date`. It uses the API's aggregate counts; a visible Cold row does not
add a participant while the mode is false. After `make dbt-run` and
`make dbt-test`, inspect the view (replace `PROJECT_ID`):

```sql
SELECT city_id, score_date, current_tipping_score, current_primary_driver,
       cold_in_global_score,
       cold_score, cold_status, cold_monitored, cold_available, cold_coverage,
       temperature_2m_min, normal_temperature_2m_min, cold_anomaly_c
FROM `PROJECT_ID.mart.mart_city_score_detail_v2`
ORDER BY city_id;
```

The unit test `test_cold_detail_v2` covers date selection, ties, Cold missingness,
zero/unmonitored states and dates outside the two-day window using complete SQL
fixtures. The warehouse test `assert_city_score_v2_worst_day_deterministic`
checks the selected run/date and all eight Cold values against history. The
existing city-spine test continues to check one detail row per configured city.

### Temporary legacy rollback marts

The unsuffixed `mart_city_score_history`, `mart_city_score_current`,
`mart_city_score_detail` and `mart_city_zone_current` relations remain during
the rollout only so the previous application can be restored without a data
rollback. They retain their legacy schema and scoring semantics, including the
old treatment of missing input. The active backend does not read them, and v2
fields such as `*_available`, `*_coverage` and monitored/available aggregate
counts must not be expected on these unsuffixed relations.

## Same-vintage ML marts with leakage controls

The new ML path starts from `stg_city_signal_vintage`. That staging model
preserves every retrieval and prevents weather, air-quality and flood values
from different ingestion runs from being combined. This is a same-vintage and
outcome-leakage-control claim, not a claim of exact provider issue time or exact
UTC lead time; the known time limits are centralized in
[Doc 0](0-critical-limitations.md#time-and-provenance-limits).

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

No realized Archive API outcome is joined into this model, so the SQL
does not itself introduce outcome leakage. It is the shared feature-definition
source for historical training and live serving. Its temporal ordering relies
on `ingested_at_utc`, a job-start availability proxy rather than the provider's
model issue time or a per-city request timestamp; it therefore supports the
documented leakage control, not an exact-availability claim.

Eligibility currently requires exactly 24 distinct weather timestamps on every
Horizon 0-4 date. If a provider response represents a DST-transition civil day
with 23 or 25 timestamps, that otherwise complete vintage is excluded from
canonical training and serving. This is a known coverage rule, not evidence that
the source day itself was incomplete.

The old `mart_ml_feature_store` remains temporarily for compatibility. Its
date-based `LEAD()` construction does not guarantee that all horizons came from
the same retrieval, so it must not be used for the new same-vintage training
path.

### `mart_city_realized_weather_daily` (table)

**Grain:** one row per `(city_id, valid_date)`.

This is the realized-label boundary. It is built from
`stg_latest_historical_daily`, whose source is lagged Open-Meteo Archive API
weather, and exposes:

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

The availability timestamps are essential. The Archive API outcome is
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

The current warehouse supports realized Open-Meteo Archive API labels for
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

> Heat and Rain use same-vintage forecast rules. The product currently labels
> Heat's Archive API backtest as limited and Rain's as insufficient skill, but
> no reproducible evaluation report is pinned in this repository.
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

Same-vintage ML path with leakage controls
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
- proxy temporal ordering: recorded label ingestion must be later than the
  forecast run's recorded ingestion time.

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

For the separate same-vintage ML path with leakage controls:

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
neither execution of the twice-daily scheduled ingestion job performs the
`dbt test` portions of steps 1 and 3; those tests need an explicit deployment or
validation run.

The MLOps workflow publishes the DVC object and commits its pointer only after
extraction, contract validation, training and registry logging succeed. Model
promotion remains a separate downstream gate; a registered version that fails
quality thresholds does not receive the `champion` alias. That rejection does
not block deployment of the explicitly declared operational rule policy.

At the current scale these marts intentionally use straightforward full-refresh
tables plus one serving view. Incremental materialization can be introduced when
warehouse volume makes it necessary; it is not required to establish correct
same-vintage lineage and the documented outcome-leakage controls.
