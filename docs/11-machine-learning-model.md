# 🤖 Module 11: Machine Learning & MLOps Pipeline (`ClimaSentinel_RiskForecaster`)

This document details the complete end-to-end architecture, mathematics, data engineering, model training, tracking, and serving infrastructure for the **ClimaSentinel Multi-Output Random Forest Risk Forecaster**. 

---

## 📐 1. Architectural Overview & Objectives

While the primary ClimaSentinel dashboard provides real-time situational awareness ($t_0$) based on factual, validated environmental signals, the **AI Tipping Forecast** module serves as an advanced predictive extension for $t_{+1}$, $t_{+2}$, and $t_{+3\text{ days}}$.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           1. FEATURE INGESTION                          │
│   BigQuery Feature Store (`mart_ml_feature_store`) via dbt Materialization│
└────────────────────────────────────┬────────────────────────────────────┘
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      2. EXTRACTION & DVC VERSIONING                     │
│    `model/extract_data.py` ──► `training_snapshot.csv` (DVC Hashed)     │
└────────────────────────────────────┬────────────────────────────────────┘
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     3. TRAINING & MLFLOW TRACKING                       │
│    `model/train.py` ──► MultiOutputRegressor(RandomForestRegressor)     │
│    Logs metrics (MAE, MSE, R2), DVC Hash, & Artifacts to DagsHub        │
└────────────────────────────────────┬────────────────────────────────────┘
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    4. IN-MEMORY CACHED MODEL SERVING                    │
│    FastAPI (`main.py`) loads once from DagsHub Registry / Pickle Fallback│
│    Computes tree-spread uncertainty bands from estimator variance       │
└────────────────────────────────────┬────────────────────────────────────┘
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    5. ON-DEMAND CLIENT INFERENCE UI                     │
│    Next.js (`/forecast`) triggers real-time calculation with loading UX  │
└─────────────────────────────────────────────────────────────────────────┘
```

### Key Design Principles:
1. **Predictive Granularity**: The `MultiOutputRegressor` fits 15 independent Random Forest outputs: five risk components (`heat`, `wind`, `rain`, `air`, and `river`) for each genuine Day +1, Day +2, and Day +3 target. The requested horizon selects its own five-output block; shorter horizons are never synthesized by forward-filling Day +3 inputs.
2. **True MLflow MLOps Integration**: Full experiment tracking, DVC data versioning, hyperparameter logging, and model registry via **DagsHub**.
3. **Uncertainty Indication**: Decision makers need to know when trees disagree. The backend inspects all $N=100$ tree estimators and reports a $1.96 \times$ tree-standard-deviation band. This is a useful model-spread signal, but it is not a calibrated 95% prediction interval and does not promise 95% empirical coverage.
4. **Serverless & Sleeping Optimization**: To prevent high latency and high cloud costs in ephemeral/sleeping environments (Railway/Cloud Run), the model artifact is downloaded exactly once on app startup and cached globally in memory.

---

## 💾 2. BigQuery Feature Store & Data Extraction

### 2.1 The dbt Materialized Feature Store (`mart_ml_feature_store`)
To prevent data leakage and ensure training-serving skew elimination, all features are pre-joined and materialized daily in BigQuery via dbt. The table combines:
* **Historical Baselines**: `current_tipping_score` ($t_0$).
* **Observed Realities**: `temperature_2m_max`, `temperature_2m_min`, `precipitation_sum_mm`, `wind_speed_10m_max`, `european_aqi_max`, `river_discharge_m3s`.
* **Meteorological Forecast Horizon**: 3-day trajectory projections (`temp_forecast_plus_1d`, `temp_forecast_plus_2d`, `temp_forecast_plus_3d`, `precip_forecast_plus_1d`, `wind_forecast_plus_1d`, etc.).
* **Entity Identifiers**: `city_id` (one-hot encoded during training).

### 2.2 Extraction Logic (`model/extract_data.py`)
The extraction script connects to BigQuery via Google Cloud Python SDK and runs rigorous validation checks before writing the training snapshot:

```python
# Handle missing river discharge gracefully (impute 0 for non-river cities)
df['river_discharge_m3s'] = df['river_discharge_m3s'].fillna(0).infer_objects(copy=False)

# Each feature-store date is joined to score history at exact +1, +2, and +3
# calendar dates, producing five component targets per horizon.
df = df.dropna(subset=["current_tipping_score", *TARGET_COLUMNS])
```

The resulting `model/data/training_snapshot.csv` is tracked by **DVC** (`.dvc` file committed to Git), ensuring that every model run can be traced back to the precise immutable data snapshot it was trained on.

The horizon labels and purged evaluation split are point-in-time correct for the
observed score dates. However, the current feature store retains the latest
weather forecast available for each valid date rather than every historical
forecast vintage. Per-horizon test metrics can therefore be optimistic until
the ingestion layer stores both forecast issue time and valid time. Promotion
gates all three horizons, but it does not by itself guarantee live accuracy.

---

## 🧠 3. Model Architecture & Training Pipeline (`model/train.py`)

### 3.1 Multi-Output Random Forest Regressor
Because the sub-scores represent distinct environmental dynamics (e.g., thermal velocity vs. hydrological flow), we wrap a Scikit-Learn `RandomForestRegressor` inside a `MultiOutputRegressor`.

$$\mathbf{y} = \begin{bmatrix} \mathbf{y}_{+1} \\ \mathbf{y}_{+2} \\ \mathbf{y}_{+3} \end{bmatrix}, \qquad \mathbf{y}_{+h} = \begin{bmatrix} y_{\text{heat},h} \\ y_{\text{wind},h} \\ y_{\text{rain},h} \\ y_{\text{air},h} \\ y_{\text{river},h} \end{bmatrix}$$

* **Hyperparameters**: `n_estimators=100`, `max_depth=10`, `random_state=42`.
* **Shared Preprocessing**: Training and serving both use `backend/app/ml_pipeline.py`. Its fitted `ColumnTransformer` median-imputes numeric fields and one-hot encodes `city_id` against the same fixed list of 10 monitored European cities.
* **Held-Out Evaluation**: The split is made on whole calendar dates, and the three days before the test window are purged so training labels cannot overlap the held-out forecast period.

### 3.2 MLflow & DagsHub Experiment Tracking
During execution, `train.py` initializes a connection to DagsHub (`https://dagshub.com/Selim-Abouleila/ClimaSentinel.mlflow`). It logs:
* **Parameters**: `n_estimators`, `max_depth`, `random_state`, `dvc_data_hash`, `git_commit`, `feature_schema_version`, and `forecast_horizons=1,2,3`.
* **Global Metrics**: Overall Mean Absolute Error (`mae`), Mean Squared Error (`mse`), and Global R² (`r2`).
* **Per-Horizon Metrics**: `mae_d1/d2/d3` and `r2_d1/d2/d3`, plus component metrics such as `r2_heat_score_d1` and `mae_heat_score_d1`. Promotion requires every horizon average and every individual component to pass the R² and MAE thresholds, preventing easy or constant targets from hiding a weak heat, wind, rain, air, or river model.
* **Model Artifact**: The full Scikit-Learn preprocessing/model pipeline is logged to the MLflow artifact repository as `random_forest_model` and registered in the Model Registry under the name **`ClimaSentinel_RiskForecaster`**. MLflow receives a signature and representative input example for the raw, pre-preprocessing feature DataFrame.

---

## ⚡ 4. FastAPI Model Serving & Uncertainty Mechanics

### 4.1 In-Memory Module-Level Caching (`backend/app/main.py`)
To maintain blazing-fast response times ($<50\text{ms}$) while supporting Railway's auto-sleeping container architecture, the backend avoids re-downloading the model from DagsHub on every incoming request.

```python
# ── Cached estimator and provenance (loaded once at first request) ─────
_cached_model: LoadedModel | None = None

def _get_ml_model():
    """Load and cache the ML model. Downloads once, reuses forever."""
    global _cached_model
    if _cached_model is not None:
        return _cached_model
    
    # 1. In development/staging, a compatible local Pipeline may be used.
    # 2. Otherwise resolve an explicit version pin or the configured alias.
    # 3. Load, validate, and cache that exact concrete registered version.
    return _cached_model
```

An explicit `MLFLOW_MODEL_VERSION` pin has first precedence. When no pin is configured, the backend resolves `MLFLOW_MODEL_ALIAS`, which defaults to `champion`, to one concrete version and loads that exact version URI. It never automatically selects the numerically highest model version. Production also skips the bundled local pickle and returns HTTP 503 when registry selection, loading, preprocessing, prediction, or spread calculation fails. Development and staging may use the local artifact or the explicitly identified `heuristic_fallback`.

Successful forecast responses expose `prediction_source` and `model_version`; `model_version` is always the concrete version actually loaded, even when selection began from an alias. `horizon_days` selects the corresponding five fitted outputs from that atomic 15-output artifact. After every horizon passes the quality gates, `model/promote.py` assigns the configured alias to the exact version returned by the training job.

### 4.2 Tree-Spread Uncertainty Bands
A standard `.predict(X)` call on a Random Forest returns the mean prediction across all trees. ClimaSentinel extracts predictions from all 100 trees to expose model disagreement and computes the displayed band as $1.96 \times \sigma$. Because Random Forest trees are correlated and the band has not been calibrated on held-out coverage, it must not be interpreted as a statistically calibrated confidence or prediction interval.

```python
# Extract tree predictions across the selected five-output horizon block.
regressor = pipeline.named_steps["regressor"]
horizon_estimators = regressor.estimators_[horizon_slice]
all_tree_preds = []
for forest in horizon_estimators:
    # Each output has its own 100-tree RandomForestRegressor.
    sub_tree_preds = [tree.predict(X_array)[0] for tree in forest.estimators_]
    all_tree_preds.append(sub_tree_preds)

# all_tree_preds is shape (5, 100)
# For each sub-score, calculate mean, std, and 95% CI bounds:
for i, name in enumerate(sub_score_names):
    sub_preds = np.array(all_tree_preds[i])
    mean_val = np.mean(sub_preds)
    std_val = np.std(sub_preds)
    margin = 1.96 * std_val
    
    ci_lower = max(0.0, round(mean_val - margin, 1))
    ci_upper = min(100.0, round(mean_val + margin, 1))
```

* **Tree disagreement**: If the trees disagree heavily, the displayed margin expands; if they align, it tightens. It describes estimator spread, not all sources of forecast error.

---

## 🖥️ 5. Next.js Client-Side On-Demand UI (`/forecast`)

### 5.1 On-Demand Calculation UX
To prevent unnecessary API calls and server wake-ups, the Next.js forecast page (`frontend/src/app/forecast/page.tsx`) operates as an interactive `"use client"` component with three distinct visual states:

1. **Empty State (Default)**: On initial page load, no city is selected. The user is presented with a sleek prompt ("Select a Region") and a map pin icon, ensuring zero backend load until explicitly requested.
2. **Calculating State (Active Inference)**: When a city pill is clicked, the UI enters a loading state displaying an animated spinner and contextual engineering text:
   > *"Calculating Forecast — Running real-time inference for **Paris, FR** across 100 decision tree estimators and computing 95% confidence intervals."*
3. **Results State**: Displays the selected horizon's estimated total risk, primary driver, baseline delta, weather trajectory, and five granular sub-score cards with uncertainty intervals.

---

## 🛠️ 6. Deployment & Operational Checklist

To successfully deploy and run the ML forecast module in any environment (Local, Staging, or Production), ensure the following environment variables and configurations are set:

### 6.1 Required Backend Environment Variables
| Variable | Description | Example / Source |
| :--- | :--- | :--- |
| `DAGSHUB_USER_TOKEN` | Authentication token for DagsHub MLflow server | `***` (DagsHub Settings ➔ Tokens) |
| `DAGSHUB_USERNAME` | Repository owner username | `Selim-Abouleila` |
| `MLFLOW_MODEL_VERSION` | Optional exact registered-model version; overrides the alias | Blank or `18` |
| `MLFLOW_MODEL_ALIAS` | Registry alias used when no exact version is pinned | `champion` |
| `GCP_PROJECT_ID` | GCP Project ID for BigQuery Feature Store | `climasentinel` |
| `BQ_DATASET` | Target BigQuery dataset containing mart tables | `mart` |

### 6.2 Verification & Debugging Commands
* **Run Feature Extraction**: `python -m model.extract_data`
* **Retrain & Log Model to DagsHub**: `python -m model.train`
* **Test FastAPI Inference Endpoint**: `curl http://127.0.0.1:8000/data/city/paris_fr/forecast`

The model-serving integration test uses a temporary SQLite-backed MLflow Registry, registers two real 15-output sklearn Pipelines, assigns `champion` to the older version, and invokes the real FastAPI route for Day +1, +2, and +3. This proves horizon selection, alias resolution, exact-version loading, preprocessing, per-tree spread, pin precedence, caching, and production failure for a missing alias without external services.

### 6.3 Audit Logs Example (Healthy Execution)
```text
2026-06-28 20:19:09,879  INFO      Accessing as Selim-Abouleila
2026-06-28 20:19:10,638  INFO      Initialized MLflow to track repo "Selim-Abouleila/ClimaSentinel"
2026-06-28 20:19:10,638  INFO      Repository Selim-Abouleila/ClimaSentinel initialized!
2026-06-28 20:19:11,102  INFO      ML model loaded from MLflow registry and cached.
INFO:     100.64.0.3:42690 - "GET /data/city/paris_fr/forecast HTTP/1.1" 200 OK
```

---
*Document Version: 1.0.0*  
*Primary Author: Selim Abouleila (Lead MLOps Engineer)*  
*Module: ClimaSentinel AI Risk Forecaster*
