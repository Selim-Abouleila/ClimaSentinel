"""Focused tests for exact multi-horizon model promotion."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


PROMOTE_PATH = Path(__file__).resolve().parents[2] / "model" / "promote.py"
PROMOTE_SPEC = importlib.util.spec_from_file_location("model_promote", PROMOTE_PATH)
assert PROMOTE_SPEC is not None and PROMOTE_SPEC.loader is not None
promote = importlib.util.module_from_spec(PROMOTE_SPEC)
PROMOTE_SPEC.loader.exec_module(promote)

VERSION_35_METRICS = {
    "r2_d1": 0.8048,
    "mae_d1": 1.5411,
    "r2_heat_score_d1": 0.6665,
    "mae_heat_score_d1": 6.7081,
    "r2_wind_score_d1": 0.9999,
    "mae_wind_score_d1": 0.0409,
    "r2_rain_score_d1": 0.9991,
    "mae_rain_score_d1": 0.0270,
    "r2_air_score_d1": 0.9985,
    "mae_air_score_d1": 0.0822,
    "r2_river_score_d1": 0.3598,
    "mae_river_score_d1": 0.8471,
    "r2_d2": 0.7762,
    "mae_d2": 1.9001,
    "r2_heat_score_d2": 0.5090,
    "mae_heat_score_d2": 8.5102,
    "r2_wind_score_d2": 0.9999,
    "mae_wind_score_d2": 0.0407,
    "r2_rain_score_d2": 0.9980,
    "mae_rain_score_d2": 0.0412,
    "r2_air_score_d2": 0.9998,
    "mae_air_score_d2": 0.0510,
    "r2_river_score_d2": 0.3742,
    "mae_river_score_d2": 0.8573,
    "r2_d3": 0.8393,
    "mae_d3": 1.8589,
    "r2_heat_score_d3": 0.5189,
    "mae_heat_score_d3": 8.4676,
    "r2_wind_score_d3": 0.9998,
    "mae_wind_score_d3": 0.0448,
    "r2_rain_score_d3": 0.9991,
    "mae_rain_score_d3": 0.0311,
    "r2_air_score_d3": 0.9996,
    "mae_air_score_d3": 0.0672,
    "r2_river_score_d3": 0.6789,
    "mae_river_score_d3": 0.6838,
}


def _multi_horizon_run(metrics_override=None):
    metrics = {
        "r2_d1": 0.80,
        "mae_d1": 2.0,
        "r2_d2": 0.75,
        "mae_d2": 2.5,
        "r2_d3": 0.70,
        "mae_d3": 3.0,
    }
    for horizon in (1, 2, 3):
        for score_name in promote.SCORE_NAMES:
            metrics[f"r2_{score_name}_d{horizon}"] = 0.70
            metrics[f"mae_{score_name}_d{horizon}"] = 3.0
    metrics.update(metrics_override or {})
    return SimpleNamespace(
        data=SimpleNamespace(
            metrics=metrics,
            params={
                "feature_schema_version": "2",
                "forecast_horizons": "1,2,3",
            },
        )
    )


def test_promotion_uses_exact_training_version_and_assigns_champion():
    client = MagicMock()
    client.get_model_version.return_value = SimpleNamespace(
        version="41",
        run_id="run-41",
    )
    client.get_run.return_value = _multi_horizon_run()

    with (
        patch.dict(
            "os.environ",
            {
                "DAGSHUB_USERNAME": "owner",
                "DAGSHUB_USER_TOKEN": "token",
                "MLFLOW_MODEL_VERSION": "41",
                "MLFLOW_MODEL_ALIAS": "champion",
            },
            clear=False,
        ),
        patch.dict(
            "sys.modules",
            {"dagshub": SimpleNamespace(init=MagicMock())},
        ),
        patch.object(promote, "MlflowClient", return_value=client),
    ):
        promote.promote_model()

    client.get_model_version.assert_called_once_with(
        "ClimaSentinel_RiskForecaster",
        "41",
    )
    client.search_model_versions.assert_not_called()
    client.transition_model_version_stage.assert_called_once_with(
        name="ClimaSentinel_RiskForecaster",
        version="41",
        stage="Production",
        archive_existing_versions=True,
    )
    client.set_registered_model_alias.assert_called_once_with(
        "ClimaSentinel_RiskForecaster",
        "champion",
        "41",
    )


def test_live_version_35_metrics_pass_score_specific_gates():
    client = MagicMock()
    client.get_model_version.return_value = SimpleNamespace(
        version="35",
        run_id="run-35",
    )
    client.get_run.return_value = _multi_horizon_run(VERSION_35_METRICS)

    with (
        patch.dict(
            "os.environ",
            {
                "DAGSHUB_USER_TOKEN": "token",
                "MLFLOW_MODEL_VERSION": "35",
            },
            clear=False,
        ),
        patch.dict(
            "sys.modules",
            {"dagshub": SimpleNamespace(init=MagicMock())},
        ),
        patch.object(promote, "MlflowClient", return_value=client),
    ):
        promote.promote_model()

    client.set_registered_model_alias.assert_called_once_with(
        "ClimaSentinel_RiskForecaster",
        "champion",
        "35",
    )


def test_promotion_rejects_candidate_when_one_horizon_fails_gate():
    client = MagicMock()
    client.get_model_version.return_value = SimpleNamespace(
        version="42",
        run_id="run-42",
    )
    client.get_run.return_value = _multi_horizon_run({"r2_d2": 0.20})

    with (
        patch.dict(
            "os.environ",
            {
                "DAGSHUB_USER_TOKEN": "token",
                "MLFLOW_MODEL_VERSION": "42",
            },
            clear=False,
        ),
        patch.dict(
            "sys.modules",
            {"dagshub": SimpleNamespace(init=MagicMock())},
        ),
        patch.object(promote, "MlflowClient", return_value=client),
        pytest.raises(SystemExit) as exit_info,
    ):
        promote.promote_model()

    assert exit_info.value.code == 1
    client.set_registered_model_alias.assert_not_called()


def test_promotion_rejects_candidate_when_one_component_fails_gate():
    client = MagicMock()
    client.get_model_version.return_value = SimpleNamespace(
        version="43",
        run_id="run-43",
    )
    client.get_run.return_value = _multi_horizon_run(
        {"r2_heat_score_d1": 0.20}
    )

    with (
        patch.dict(
            "os.environ",
            {
                "DAGSHUB_USER_TOKEN": "token",
                "MLFLOW_MODEL_VERSION": "43",
            },
            clear=False,
        ),
        patch.dict(
            "sys.modules",
            {"dagshub": SimpleNamespace(init=MagicMock())},
        ),
        patch.object(promote, "MlflowClient", return_value=client),
        pytest.raises(SystemExit) as exit_info,
    ):
        promote.promote_model()

    assert exit_info.value.code == 1
    client.set_registered_model_alias.assert_not_called()


@pytest.mark.parametrize(
    "metric_override",
    (
        {"mae_heat_score_d2": 10.01},
        {"mae_wind_score_d2": 7.01},
    ),
    ids=("heat-above-ten", "non-heat-above-seven"),
)
def test_promotion_rejects_component_mae_above_score_limit(metric_override):
    client = MagicMock()
    client.get_model_version.return_value = SimpleNamespace(
        version="44",
        run_id="run-44",
    )
    client.get_run.return_value = _multi_horizon_run(metric_override)

    with (
        patch.dict(
            "os.environ",
            {
                "DAGSHUB_USER_TOKEN": "token",
                "MLFLOW_MODEL_VERSION": "44",
            },
            clear=False,
        ),
        patch.dict(
            "sys.modules",
            {"dagshub": SimpleNamespace(init=MagicMock())},
        ),
        patch.object(promote, "MlflowClient", return_value=client),
        pytest.raises(SystemExit) as exit_info,
    ):
        promote.promote_model()

    assert exit_info.value.code == 1
    client.set_registered_model_alias.assert_not_called()
