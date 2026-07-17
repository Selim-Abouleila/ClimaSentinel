"""Focused tests for multi-horizon training and workflow output handoff."""

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
    FORECAST_HORIZONS,
    NUMERIC_FEATURE_COLUMNS,
    TARGET_COLUMNS_BY_HORIZON,
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
    frame["date"] = np.repeat(dates, len(ALL_CITIES)).astype(str)
    frame["city_id"] = list(ALL_CITIES) * len(dates)
    for horizon in FORECAST_HORIZONS:
        for target_index, target in enumerate(
            TARGET_COLUMNS_BY_HORIZON[horizon]
        ):
            frame[target] = (
                horizon * 20.0
                + frame[NUMERIC_FEATURE_COLUMNS[target_index]] * 0.1
                + rng.normal(0.0, 0.2, row_count)
            )
    return frame


def test_training_logs_each_horizon_and_exports_exact_registered_version(tmp_path):
    logged_metrics = {}
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

    with (
        patch.object(train.pd, "read_csv", return_value=_training_frame()),
        patch.object(train, "build_model_pipeline", side_effect=tiny_builder),
        patch.object(train, "get_git_commit", return_value="abc123"),
        patch.object(train, "get_dvc_hash", return_value="dvc123"),
        patch.object(train.dagshub, "init"),
        patch.object(train.mlflow, "set_experiment"),
        patch.object(train.mlflow, "start_run", return_value=nullcontext()),
        patch.object(train.mlflow, "log_params"),
        patch.object(train.mlflow, "log_param"),
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

    assert {f"r2_d{horizon}" for horizon in FORECAST_HORIZONS} <= logged_metrics.keys()
    assert {f"mae_d{horizon}" for horizon in FORECAST_HORIZONS} <= logged_metrics.keys()
    assert {
        f"mae_{target.removeprefix('future_').removesuffix(f'_{horizon}d')}_d{horizon}"
        for horizon in FORECAST_HORIZONS
        for target in TARGET_COLUMNS_BY_HORIZON[horizon]
    } <= logged_metrics.keys()
    logged_estimator = log_model.call_args.kwargs["sk_model"]
    assert len(logged_estimator.named_steps["regressor"].estimators_) == 15
    assert github_output.read_text() == "model_version=77\n"
