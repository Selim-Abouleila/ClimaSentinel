# 4. Mart Layer (Gold)

The mart layer represents the Gold standard of the medallion architecture. It consumes the clean, harmonized signals from the Silver layer (`stg`) and applies business logic to generate the core deliverable of ClimaSentinel: the **Tipping Score**.

## Purpose

The mart layer answers three specific operational questions:
1. **What is the current tension for each city?** (Tipping Score 0-100)
2. **Which cities require immediate action?** (Ranking & Zones)
3. **Why is the score high?** (Primary Driver Attribution)

---

## Dataset

All models in this layer are deployed to the **`mart`** BigQuery dataset.

---

## Models

### 1. `mart_city_score_history` (Table)

This is the core calculation engine. It evaluates the 7-day forecast for every city against historical norms and physical thresholds.

It is materialized as a **Table** to support fast, historical trend analysis in dashboarding tools (e.g., Looker, Tableau).

#### The Tipping Score Logic
The score is calculated across 5 factors using both absolute physics and relative auto-calibration.

| Factor | Logic | Formula |
|---|---|---|
| **🌡️ Heat** | Relative (Anomaly + Velocity) | `(Forecast - Normal) * 5 + Positive_24h_Jump * 5` |
| **💨 Wind** | Absolute Threshold | `(Gusts - 40km/h) * 2.5` |
| **🌧️ Rain** | Absolute Volume | `Daily Precipitation (mm) * 2` |
| **🌫️ Air Quality** | Direct Mapping | `European AQI Max` |
| **🌊 River** | Velocity Spikes | `24h River Volume % Increase * 200` |

#### The Global Score
Instead of averaging (which hides risk), the `global_tipping_score` is the **MAX()** of the 5 factor scores. The factor that triggers the max score is tagged as the `primary_driver`.

> **Note on Auto-calibration (The Join):** 
> To calculate the Heat anomaly, this model performs a `LEFT JOIN` against `stg.city_monthly_normals` (the 10-year baseline table built via `dbt seed`). The join uses `city_id` and the extracted `MONTH(date)` to ensure geographically accurate comparisons.

---

### 2. `mart_city_score_current` (View)

This is the "Dashboard Landing Page". It filters the history table down to a rolling **48-hour operational window** (Today and Tomorrow).

*   **Metric:** Extracts the highest tipping score expected over the next 48 hours.
*   **Ranking:** Ranks the 10 cities from 1 (Most Critical) to 10 (Most Stable) using `RANK() OVER (ORDER BY current_tipping_score DESC)`.

---

### 3. `mart_city_zone_current` (View)

This model aggregates the current scores into a high-level executive summary by categorizing cities into 4 operational zones.

| Zone | Score Range | Meaning |
|---|---|---|
| 🔴 **Critical** | 81 - 100 | Severe operational risk. Immediate action required. |
| 🟠 **Tipping** | 61 - 80 | Tension rising rapidly. Preparations needed. |
| 🟡 **Monitoring**| 31 - 60 | Elevated signals, but within manageable bounds. |
| 🟢 **Stable** | 0 - 30 | Normal operations. |

**Outputs:** Number of cities in each zone, a comma-separated list of those cities, and the primary drivers causing the tension.

---

## Schema Tests

The following tests are defined in `_mart_models.yml` and run automatically during `make deploy`:

*   `city_id` and `date`: `not_null`
*   `global_tipping_score`: `not_null`
*   `zone_name`: `not_null` and `unique` (ensures exact aggregation)
