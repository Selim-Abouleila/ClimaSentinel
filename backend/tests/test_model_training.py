"""Focused tests for honest six-output Heat/Rain model training."""

from contextlib import nullcontext
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd

from app.ml_pipeline import (
    ALL_CITIES,
    FEATURE_SCHEMA_VERSION,
    FORECAST_HORIZONS,
    MAX_LABEL_LOOKAHEAD_DAYS,
    NUMERIC_FEATURE_COLUMNS,
    REGISTERED_MODEL_NAME,
    TARGET_COLUMNS,
    TARGET_COLUMNS_BY_HORIZON,
    TARGET_SCHEMA_VERSION,
    TRAINING_DATA_CONTRACT,
    build_model_pipeline,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TRAIN_PATH = REPOSITORY_ROOT / "model" / "train.py"
TRAIN_SPEC = importlib.util.spec_from_file_location("model_train", TRAIN_PATH)
assert TRAIN_SPEC is not None and TRAIN_SPEC.loader is not None
sys.path.insert(0, str(REPOSITORY_ROOT))
try:
    with patch.dict(
        "sys.modules",
        {"dagshub": SimpleNamespace(init=MagicMock())},
    ):
        train = importlib.util.module_from_spec(TRAIN_SPEC)
        TRAIN_SPEC.loader.exec_module(train)
finally:
    sys.path.remove(str(REPOSITORY_ROOT))


def _training_frame() -> pd.DataFrame:
    rng = np.random.default_rng(42)
    dates = pd.date_range("2026-01-01", periods=15, freq="D")
    row_count = len(dates) * len(ALL_CITIES)
    frame = pd.DataFrame(
        {
            column: rng.normal(index + 20.0, 2.0, row_count)
            for index, column in enumerate(NUMERIC_FEATURE_COLUMNS)
        }
    )
    frame["forecast_origin_date"] = np.repeat(dates, len(ALL_CITIES)).astype(str)
    frame["city_id"] = list(ALL_CITIES) * len(dates)
    frame["ingestion_run_id"] = [f"forecast-{index}" for index in range(row_count)]
    frame["ingested_at_utc"] = (
        pd.to_datetime(frame["forecast_origin_date"])
        + pd.Timedelta(6, unit="h")
    ).dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    frame["forecast_origin_time_zone"] = "UTC"
    frame["label_source"] = train.LABEL_SOURCE
    frame["supported_target_components"] = train.SUPPORTED_TARGET_COMPONENTS
    frame["unsupported_target_components"] = train.UNSUPPORTED_TARGET_COMPONENTS
    frame["canonical_vintage_rule"] = train.CANONICAL_VINTAGE_RULE

    origin_timestamps = pd.to_datetime(frame["forecast_origin_date"])
    for horizon in FORECAST_HORIZONS:
        target_dates = origin_timestamps + pd.Timedelta(horizon, unit="D")
        realized_available = target_dates + pd.Timedelta(1, unit="D")
        next_day_available = target_dates + pd.Timedelta(36, unit="h")
        frame[f"target_date_{horizon}d"] = target_dates.dt.strftime("%Y-%m-%d")
        frame[f"realized_weather_ingestion_run_id_{horizon}d"] = [
            f"realized-{horizon}-{index}" for index in range(row_count)
        ]
        frame[f"realized_weather_ingested_at_utc_{horizon}d"] = (
            realized_available.dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        )
        frame[f"next_day_weather_ingestion_run_id_{horizon}d"] = [
            f"next-{horizon}-{index}" for index in range(row_count)
        ]
        frame[f"next_day_weather_ingested_at_utc_{horizon}d"] = (
            next_day_available.dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        )
        frame[f"heat_label_available_at_utc_{horizon}d"] = (
            next_day_available.dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        )
        frame[f"rain_label_available_at_utc_{horizon}d"] = (
            realized_available.dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        )
        frame[f"labels_available_at_utc_{horizon}d"] = (
            next_day_available.dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        )
        frame[f"future_heat_score_{horizon}d"] = np.clip(
            10.0
            + horizon * 5.0
            + frame["temperature_2m_max"] * 0.2
            + rng.normal(0.0, 0.2, row_count),
            0.0,
            100.0,
        )
        frame[f"future_rain_score_{horizon}d"] = np.clip(
            horizon
            + frame["precipitation_sum_mm"].abs() * 0.15
            + rng.normal(0.0, 0.1, row_count),
            0.0,
            100.0,
        )
    frame["training_labels_available_at_utc"] = (
        origin_timestamps + pd.Timedelta(108, unit="h")
    ).dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Optional serving features stay null in the extracted snapshot and are
    # imputed only by the fitted pipeline.
    frame.loc[frame.index[::7], "european_aqi_max"] = np.nan
    frame.loc[frame.index[::9], "river_discharge_m3s"] = np.nan
    return frame


def test_training_logs_realized_contract_and_exports_exact_registered_version(
    tmp_path,
):
    logged_metrics = {}
    logged_params = {}
    github_output = tmp_path / "github-output.txt"
    real_builder = build_model_pipeline

    def tiny_builder(params):
        return real_builder(
            {
                **params,
                "n_estimators": 2,
                "max_depth": 2,
                "n_jobs": 1,
            }
        )

    def capture_params(params):
        logged_params.update({key: str(value) for key, value in params.items()})

    with (
        patch.object(train.pd, "read_csv", return_value=_training_frame()),
        patch.object(train, "build_model_pipeline", side_effect=tiny_builder),
        patch.object(train, "get_git_commit", return_value="a" * 40),
        patch.object(train, "get_dvc_hash", return_value="b" * 32),
        patch.object(train.dagshub, "init"),
        patch.object(train.mlflow, "set_experiment"),
        patch.object(train.mlflow, "start_run", return_value=nullcontext()),
        patch.object(train.mlflow, "log_params", side_effect=capture_params),
        patch.object(
            train.mlflow,
            "log_metric",
            side_effect=lambda name, value: logged_metrics.__setitem__(name, value),
        ),
        patch.object(
            train.mlflow.sklearn,
            "log_model",
            return_value=SimpleNamespace(registered_model_version="77"),
        ) as log_model,
        patch.object(train.joblib, "dump"),
        patch.object(train.os, "makedirs"),
        patch.dict(
            "os.environ",
            {
                "DAGSHUB_USER_TOKEN": "token",
                "GITHUB_OUTPUT": str(github_output),
            },
            clear=False,
        ),
    ):
        train.train_model()

    assert logged_params["feature_schema_version"] == FEATURE_SCHEMA_VERSION
    assert logged_params["target_schema_version"] == TARGET_SCHEMA_VERSION
    assert logged_params["training_data_contract"] == TRAINING_DATA_CONTRACT
    assert logged_params["registered_model_name"] == REGISTERED_MODEL_NAME
    assert logged_params["target_columns"] == ",".join(TARGET_COLUMNS)
    assert logged_params["supported_target_components"] == "heat,rain"
    assert logged_params["unsupported_target_components"] == "wind,air,river"
    assert logged_params["purge_gap_days"] == str(MAX_LABEL_LOOKAHEAD_DAYS)
    assert logged_params["train_rows"] == "80"
    assert logged_params["test_rows"] == "30"
    assert logged_params["test_distinct_origin_dates"] == "3"

    for horizon in FORECAST_HORIZONS:
        assert f"r2_d{horizon}" in logged_metrics
        assert f"mae_d{horizon}" in logged_metrics
        for target in TARGET_COLUMNS_BY_HORIZON[horizon]:
            score_name = target.removeprefix("future_").removesuffix(
                f"_{horizon}d"
            )
            assert f"r2_{score_name}_d{horizon}" in logged_metrics
            assert f"mae_{score_name}_d{horizon}" in logged_metrics
            assert logged_metrics[f"test_count_{score_name}_d{horizon}"] == 30
            assert logged_metrics[f"test_std_{score_name}_d{horizon}"] > 0

    logged_estimator = log_model.call_args.kwargs["sk_model"]
    assert len(logged_estimator.named_steps["regressor"].estimators_) == 6
    assert log_model.call_args.kwargs["registered_model_name"] == REGISTERED_MODEL_NAME
    assert log_model.call_args.kwargs["name"] == "random_forest_model"
    assert github_output.read_text() == "model_version=77\n"
