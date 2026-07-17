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


FEATURE_SCHEMA_VERSION = "1"

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

TARGET_COLUMNS = (
    "future_heat_score_3d",
    "future_wind_score_3d",
    "future_rain_score_3d",
    "future_air_score_3d",
    "future_river_score_3d",
)

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
                SimpleImputer(strategy="median"),
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

    return Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            (
                "regressor",
                MultiOutputRegressor(RandomForestRegressor(**params)),
            ),
        ]
    )


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
) -> tuple[np.ndarray, np.ndarray]:
    """Return point predictions and per-output tree standard deviations."""
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

    return predictions, ensemble_stds
