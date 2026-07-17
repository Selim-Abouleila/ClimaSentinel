# 4. Mart Layer (Gold)

The mart layer represents the Gold standard of the medallion architecture. It consumes the clean, harmonized signals from the Silver layer (`stg`) and applies business logic to generate the core deliverable of ClimaSentinel: the **Tipping Score**.

## Purpose

The mart layer answers five specific operational questions:
1. **What is the current tension for each city?** (Tipping Score 0-100)
2. **Which cities require immediate action?** (Ranking & Zones)
3. **Why is the score high?** (Primary Driver Attribution)
4. **What are the individual sub-scores?** (Heat, Wind, Rain, Air, River breakdown)
5. **What will the tension look like in 3 days?** (ML Feature Store for forecasting)

---

## Dataset

All models in this layer are deployed to the **`mart`** BigQuery dataset.

> **Note on materialization:** The `dbt_project.yml` default for `mart.*` is `materialized: table`, but several models override this to `view` at the model level. The exact materialization of each model is annotated below.

---

## Models

### 1. `mart_city_score_history` (Table)

This is the core calculation engine. It evaluates the 7-day forecast for every city against historical norms and physical thresholds.

It is materialized as a **Table** (partitioned by `date`) to support fast, historical trend analysis in dashboarding tools (e.g., Looker, Tableau).

#### The Tipping Score Logic
The score is calculated across 5 factors using both absolute physics and relative auto-calibration.

| Factor | Logic | Formula |
|---|---|---|
| **🌡️ Heat** | Relative (Anomaly + Velocity) | `(Forecast - Normal) * 5 + Positive_24h_Jump * 5` |
| **💨 Wind** | Absolute Threshold | `(Gusts - 40km/h) * 2.5` |
| **🌧️ Rain** | Absolute Volume | `Daily Precipitation (mm) * 2` |
| **🌫️ Air Quality** | Threshold (EU "Moderate") | `(AQI - 40) * 1.67` (forward-filled if sensor drops out) |
| **🌊 River** | Velocity Spikes | `24h River Volume % Increase * 200` |

#### The Global Score
Instead of averaging (which hides risk), the `global_tipping_score` is the **MAX()** of the 5 factor scores. The factor that triggers the max score is tagged as the `primary_driver`.

> **Note on Auto-calibration (The Join):** 
> To calculate the Heat anomaly, this model performs a `LEFT JOIN` against `stg.city_monthly_normals` (the 10-year baseline table built via `dbt seed`). The join uses `city_id` and the extracted `MONTH(date)` to ensure geographically accurate comparisons.
> 
> **Example (Relative Geography):** If the forecast is 35°C in both Paris and Madrid in the summer:
> - In **Madrid**, the historical normal might be 33°C. The anomaly is small (+2°C), resulting in a **low** heat score.
> - In **Paris**, the historical normal might be 25°C. The anomaly is massive (+10°C), resulting in a **critical** heat score.
> 
> This ensures hot climates aren't constantly flagged with false alarms while identifying dangerous anomalies in historically cooler regions.

---

### 2. `mart_city_score_current` (View)

This is the "Dashboard Landing Page". It filters the history table down to a rolling **48-hour operational window** (Today and Tomorrow).

*   **Materialization:** **View** (overrides the dbt_project.yml default). Always fresh, no refresh needed.
*   **Metric:** Extracts the highest tipping score expected over the next 48 hours.
*   **Ranking:** Ranks the 10 cities from 1 (Most Critical) to 10 (Most Stable) using `RANK() OVER (ORDER BY current_tipping_score DESC)`.

---

### 3. `mart_city_zone_current` (View)

This model aggregates the current scores into a high-level executive summary by categorizing cities into 4 operational zones.

*   **Materialization:** **View** (overrides the dbt_project.yml default).

| Zone | Score Range | Meaning |
|---|---|---|
| 🔴 **Critical** | 81 - 100 | Severe operational risk. Immediate action required. |
| 🟠 **Tipping** | 61 - 80 | Tension rising rapidly. Preparations needed. |
| 🟡 **Monitoring**| 31 - 60 | Elevated signals, but within manageable bounds. |
| 🟢 **Stable** | 0 - 30 | Normal operations. |

**Outputs:** Number of cities in each zone, a comma-separated list of those cities, and the primary drivers causing the tension.

---

### 4. `mart_city_score_detail` (View)

Exposes the five individual tipping sub-scores (Heat, Wind, Rain, Air Quality, River) plus raw signal values for every city within the current 48-hour operational window. One row per city — the day with the highest global tipping score is selected so all sub-scores are internally consistent.

*   **Materialization:** **View** (overrides the dbt_project.yml default).
*   **Source:** `mart_city_score_history` (NOT `mart_city_score_current` — kept fully independent so existing dashboard is unaffected).
*   **Consumer:** `GET /data/city/{city_id}/scores` (FastAPI backend endpoint powering the city detail page).

| Column | Description |
|---|---|
| `current_tipping_score` | Global tipping score (0-100): maximum of the 5 sub-scores on the worst day |
| `current_primary_driver` | The factor responsible for the highest score |
| `heat_score` | Heat sub-score (0-100): based on temperature anomaly and positive velocity |
| `wind_score` | Wind sub-score (0-100): based on gust speed above 40 km/h threshold |
| `rain_score` | Rain sub-score (0-100): based on daily precipitation sum |
| `air_score` | Air Quality sub-score (0-100): threshold at EU "Moderate" (AQI > 40), scaled via `(AQI - 40) * 1.67`. Forward-fills last known AQI if sensor data is missing. |
| `river_score` | River/Flood sub-score (0-100): based on positive river discharge velocity |
| `temperature_2m_max`, `wind_gusts_10m_max`, `precipitation_sum_mm`, `european_aqi_max`, `river_discharge_m3s` | Raw signal context values for tooltip display in the UI |

---

### 5. `mart_ml_feature_store` (Table)

Single source of truth Feature Store for MLOps training and serving. Pre-computes three-day weather trajectories and aligns them with separate Day +1, Day +2, and Day +3 component-score targets.

*   **Materialization:** **Table** (partitioned by `date`).
*   **Sources:** `stg_city_signal_input` (Silver layer) + `mart_city_score_history` (Gold layer).
*   **Consumer:** `model/train.py` (training pipeline) and `GET /data/city/{city_id}/forecast` (FastAPI backend for inference).

| Feature Group | Columns |
|---|---|
| **Current weather (t₀)** | `temperature_2m_max`, `temperature_2m_min`, `precipitation_sum_mm`, `wind_speed_10m_max`, `european_aqi_max`, `river_discharge_m3s` |
| **Forecast trajectory (t+1…t+3)** | `temp_forecast_plus_1d/2d/3d`, `precip_forecast_plus_1d/2d/3d`, `wind_forecast_plus_1d/2d/3d` |
| **Baseline** | `current_tipping_score` (from `mart_city_score_history`) |
| **Targets (Multi-Output)** | Five component targets plus the total target at each suffix: `*_1d`, `*_2d`, and `*_3d` |

---

## Model Dependency Graph

```
stg_city_signal_input ──→ mart_city_score_history ──→ mart_city_score_current ──→ mart_city_zone_current
         │                         │
         │                         ├──→ mart_city_score_detail
         │                         │
         └────────────────────────►├──→ mart_ml_feature_store
```

---

## Schema Tests

The following tests are defined in `_mart_models.yml` and run automatically during `make deploy`:

*   `city_id` and `date`: `not_null` (on `mart_city_score_history`, `mart_ml_feature_store`)
*   `global_tipping_score`: `not_null`
*   `zone_name`: `not_null` and `unique` (ensures exact aggregation)
*   `current_tipping_score`: `not_null` (on `mart_city_score_current`, `mart_city_score_detail`)
*   `city_id`: `not_null` and `unique` (on `mart_city_score_current`, `mart_city_score_detail`)
