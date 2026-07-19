"""Shared raw-feature preprocessing and multi-output model utilities."""

from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.multioutput import MultiOutputRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder


FEATURE_SCHEMA_VERSION = "3"
TARGET_SCHEMA_VERSION = "realized_heat_rain_v1"
TRAINING_DATA_CONTRACT = "mart_ml_training_examples_v1"
REGISTERED_MODEL_NAME = "ClimaSentinel_HeatRainForecaster"

FORECAST_HORIZONS = (1, 2, 3)
TARGET_SCORE_NAMES = ("heat", "rain")
RULE_BASED_SCORE_NAMES = ("wind", "air", "river")
MAX_LABEL_LOOKAHEAD_DAYS = max(FORECAST_HORIZONS) + 1

NUMERIC_FEATURE_COLUMNS = (
    "current_tipping_score",
    "normal_temperature_2m_max",
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_sum_mm",
    "wind_speed_10m_max",
    "wind_gusts_10m_max",
    "european_aqi_max",
    "river_discharge_m3s",
    "temp_forecast_plus_1d",
    "temp_forecast_plus_2d",
    "temp_forecast_plus_3d",
    "temp_forecast_plus_4d",
    "precip_forecast_plus_1d",
    "precip_forecast_plus_2d",
    "precip_forecast_plus_3d",
    "wind_forecast_plus_1d",
    "wind_forecast_plus_2d",
    "wind_forecast_plus_3d",
    "wind_gusts_forecast_plus_1d",
    "wind_gusts_forecast_plus_2d",
    "wind_gusts_forecast_plus_3d",
    "aqi_forecast_plus_1d",
    "aqi_forecast_plus_2d",
    "aqi_forecast_plus_3d",
    "river_forecast_plus_1d",
    "river_forecast_plus_2d",
    "river_forecast_plus_3d",
    "river_forecast_plus_4d",
)

CATEGORICAL_FEATURE_COLUMNS = ("city_id",)
FEATURE_COLUMNS = NUMERIC_FEATURE_COLUMNS + CATEGORICAL_FEATURE_COLUMNS

TARGET_COLUMNS_BY_HORIZON = {
    horizon: tuple(
        f"future_{score_name}_score_{horizon}d"
        for score_name in TARGET_SCORE_NAMES
    )
    for horizon in FORECAST_HORIZONS
}

TARGET_COLUMNS = tuple(
    target
    for horizon in FORECAST_HORIZONS
    for target in TARGET_COLUMNS_BY_HORIZON[horizon]
)

OUTPUTS_PER_HORIZON = len(TARGET_SCORE_NAMES)

ALL_CITIES = (
    "amsterdam_nl",
    "athens_gr",
    "berlin_de",
    "lisbon_pt",
    "london_gb",
    "madrid_es",
    "paris_fr",
    "rome_it",
    "stockholm_se",
    "warsaw_pl",
)


class ModelCompatibilityError(ValueError):
    """Raised when a serialized estimator is not the shared fitted pipeline."""


def output_slice_for_horizon(horizon_days: int) -> slice:
    """Return the learned Heat/Rain slice belonging to one forecast horizon."""
    if horizon_days not in FORECAST_HORIZONS:
        raise ModelCompatibilityError(
            f"Unsupported forecast horizon {horizon_days}; expected one of "
            f"{FORECAST_HORIZONS}"
        )
    start = FORECAST_HORIZONS.index(horizon_days) * OUTPUTS_PER_HORIZON
    return slice(start, start + OUTPUTS_PER_HORIZON)


def chronological_purged_split(
    features: pd.DataFrame,
    targets: pd.DataFrame,
    dates: pd.Series,
    test_fraction: float = 0.2,
    purge_days: int = MAX_LABEL_LOOKAHEAD_DAYS,
):
    """Split on dates and purge every label dependency crossing the test window."""
    parsed_dates = pd.to_datetime(dates, errors="raise")
    unique_dates = pd.Index(parsed_dates.unique()).sort_values()
    if len(unique_dates) < 6:
        raise ValueError("At least six distinct dates are required for a purged split")
    if not 0.0 < test_fraction < 1.0:
        raise ValueError("test_fraction must be strictly between zero and one")

    split_index = min(
        len(unique_dates) - 1,
        max(1, int(len(unique_dates) * (1.0 - test_fraction))),
    )
    test_start = pd.Timestamp(unique_dates[split_index])
    purge_boundary = test_start - pd.Timedelta(purge_days, unit="D")
    train_mask = parsed_dates < purge_boundary
    test_mask = parsed_dates >= test_start
    if not train_mask.any() or not test_mask.any():
        raise ValueError("Purged chronological split produced an empty partition")

    return (
        features.loc[train_mask].reset_index(drop=True),
        features.loc[test_mask].reset_index(drop=True),
        targets.loc[train_mask].reset_index(drop=True),
        targets.loc[test_mask].reset_index(drop=True),
        test_start,
    )


def prepare_feature_frame(
    data: pd.DataFrame | pd.Series | Mapping[str, Any],
) -> pd.DataFrame:
    """Validate, coerce, and order raw model features for training or serving."""
    if isinstance(data, pd.DataFrame):
        frame = data.copy()
    elif isinstance(data, pd.Series):
        frame = data.to_frame().T
    elif isinstance(data, Mapping):
        frame = pd.DataFrame([dict(data)])
    else:
        try:
            frame = pd.DataFrame(data)
        except Exception as exc:
            raise ValueError("Model input must be a pandas DataFrame or row mapping") from exc

    missing_columns = [column for column in FEATURE_COLUMNS if column not in frame.columns]
    if missing_columns:
        raise ValueError(
            "Missing required model feature columns: " + ", ".join(missing_columns)
        )

    prepared = frame.loc[:, list(FEATURE_COLUMNS)].copy()
    for column in NUMERIC_FEATURE_COLUMNS:
        prepared[column] = pd.to_numeric(
            prepared[column], errors="coerce"
        ).astype("float64")
    prepared["city_id"] = prepared["city_id"].astype("string")
    return prepared


def build_model_pipeline(model_params: Mapping[str, Any] | None = None) -> Pipeline:
    """Build the complete raw-feature preprocessing and regression pipeline."""
    params = dict(model_params or {})

    preprocessor = ColumnTransformer(
        transformers=[
            (
                "numeric",
                SimpleImputer(strategy="median", add_indicator=True),
                list(NUMERIC_FEATURE_COLUMNS),
            ),
            (
                "city",
                OneHotEncoder(
                    categories=[list(ALL_CITIES)],
                    handle_unknown="ignore",
                    drop="first",
                    sparse_output=False,
                ),
                list(CATEGORICAL_FEATURE_COLUMNS),
            ),
        ],
        remainder="drop",
    )

    pipeline = Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            (
                "regressor",
                MultiOutputRegressor(RandomForestRegressor(**params)),
            ),
        ]
    )
    # Persist the ordered semantic contract inside the artifact itself. MLflow
    # run parameters are useful for promotion, but they are not sufficient to
    # prove that a loaded six-output estimator uses the expected target order.
    pipeline.climasentinel_feature_schema_version = FEATURE_SCHEMA_VERSION
    pipeline.climasentinel_target_schema_version = TARGET_SCHEMA_VERSION
    pipeline.climasentinel_training_data_contract = TRAINING_DATA_CONTRACT
    pipeline.climasentinel_forecast_horizons = FORECAST_HORIZONS
    pipeline.climasentinel_target_columns = TARGET_COLUMNS
    pipeline.climasentinel_target_score_names = TARGET_SCORE_NAMES
    return pipeline


def validate_fitted_pipeline(model: Any) -> Pipeline:
    """Validate that a loaded artifact supports shared preprocessing and spread."""
    if not isinstance(model, Pipeline):
        raise ModelCompatibilityError(
            "Incompatible model artifact: expected a fitted sklearn Pipeline"
        )

    missing_steps = {
        step for step in ("preprocessor", "regressor") if step not in model.named_steps
    }
    if missing_steps:
        raise ModelCompatibilityError(
            "Incompatible model artifact: missing pipeline steps "
            + ", ".join(sorted(missing_steps))
        )

    expected_contract = {
        "climasentinel_feature_schema_version": FEATURE_SCHEMA_VERSION,
        "climasentinel_target_schema_version": TARGET_SCHEMA_VERSION,
        "climasentinel_training_data_contract": TRAINING_DATA_CONTRACT,
        "climasentinel_forecast_horizons": FORECAST_HORIZONS,
        "climasentinel_target_columns": TARGET_COLUMNS,
        "climasentinel_target_score_names": TARGET_SCORE_NAMES,
    }
    for attribute, expected_value in expected_contract.items():
        actual_value = getattr(model, attribute, None)
        if actual_value != expected_value:
            raise ModelCompatibilityError(
                "Incompatible model artifact: contract field "
                f"{attribute} does not match"
            )

    preprocessor = model.named_steps["preprocessor"]
    if not isinstance(preprocessor, ColumnTransformer):
        raise ModelCompatibilityError(
            "Incompatible model artifact: preprocessor must be ColumnTransformer"
        )
    try:
        fitted_transformers = {
            name: (transformer, tuple(columns))
            for name, transformer, columns in preprocessor.transformers_
        }
        _, numeric_columns = fitted_transformers["numeric"]
        city_encoder, categorical_columns = fitted_transformers["city"]
        fitted_city_categories = tuple(city_encoder.categories_[0])
    except Exception as exc:
        raise ModelCompatibilityError(
            "Incompatible model artifact: preprocessing schema is not fitted"
        ) from exc

    if numeric_columns != NUMERIC_FEATURE_COLUMNS:
        raise ModelCompatibilityError(
            "Incompatible model artifact: numeric feature schema does not match"
        )
    if categorical_columns != CATEGORICAL_FEATURE_COLUMNS:
        raise ModelCompatibilityError(
            "Incompatible model artifact: categorical feature schema does not match"
        )
    if fitted_city_categories != ALL_CITIES:
        raise ModelCompatibilityError(
            "Incompatible model artifact: fixed city categories do not match"
        )

    regressor = model.named_steps["regressor"]
    if not isinstance(regressor, MultiOutputRegressor):
        raise ModelCompatibilityError(
            "Incompatible model artifact: regressor must be MultiOutputRegressor"
        )

    output_estimators = getattr(regressor, "estimators_", None)
    if output_estimators is None or len(output_estimators) != len(TARGET_COLUMNS):
        raise ModelCompatibilityError(
            f"Incompatible model artifact: expected {len(TARGET_COLUMNS)} fitted "
            "output estimators"
        )

    for output_index, output_forest in enumerate(output_estimators):
        trees = getattr(output_forest, "estimators_", None)
        if trees is None or not trees:
            raise ModelCompatibilityError(
                "Incompatible model artifact: output estimator "
                f"{output_index} does not expose fitted decision trees"
            )

    return model


def predict_with_ensemble_spread(
    model: Any,
    raw_features: pd.DataFrame | pd.Series | Mapping[str, Any],
    horizon_days: int | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Return predictions and tree spread for all outputs or one horizon."""
    pipeline = validate_fitted_pipeline(model)
    feature_frame = prepare_feature_frame(raw_features)
    expected_shape = (len(feature_frame), len(TARGET_COLUMNS))

    try:
        predictions = np.asarray(pipeline.predict(feature_frame), dtype=float)
        transformed_features = pipeline.named_steps["preprocessor"].transform(
            feature_frame
        )
    except Exception as exc:
        raise ModelCompatibilityError(
            "The loaded model cannot process the authoritative raw feature schema"
        ) from exc

    if predictions.shape != expected_shape:
        raise ModelCompatibilityError(
            f"Invalid prediction shape {predictions.shape}; expected {expected_shape}"
        )

    per_output_stds = []
    regressor = pipeline.named_steps["regressor"]
    try:
        for output_forest in regressor.estimators_:
            per_tree_predictions = np.vstack(
                [
                    tree.predict(transformed_features)
                    for tree in output_forest.estimators_
                ]
            )
            per_output_stds.append(per_tree_predictions.std(axis=0))
    except Exception as exc:
        raise ModelCompatibilityError(
            "The loaded model does not expose compatible per-output tree estimators"
        ) from exc

    try:
        ensemble_stds = np.stack(per_output_stds, axis=1)
    except Exception as exc:
        raise ModelCompatibilityError(
            "The loaded model produced incompatible per-output spread shapes"
        ) from exc
    if ensemble_stds.shape != expected_shape:
        raise ModelCompatibilityError(
            f"Invalid ensemble spread shape {ensemble_stds.shape}; expected {expected_shape}"
        )
    if not np.isfinite(predictions).all() or not np.isfinite(ensemble_stds).all():
        raise ModelCompatibilityError("Model predictions and spread must be finite")

    if horizon_days is None:
        return predictions, ensemble_stds

    horizon_slice = output_slice_for_horizon(horizon_days)
    return predictions[:, horizon_slice], ensemble_stds[:, horizon_slice]
