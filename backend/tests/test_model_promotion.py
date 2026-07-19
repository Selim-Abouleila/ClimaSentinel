"""Focused tests for exact six-output Heat/Rain model promotion."""

import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.ml_pipeline import (
    FEATURE_SCHEMA_VERSION,
    FORECAST_HORIZONS,
    REGISTERED_MODEL_NAME,
    TARGET_COLUMNS,
    TARGET_SCHEMA_VERSION,
    TRAINING_DATA_CONTRACT,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PROMOTE_PATH = REPOSITORY_ROOT / "model" / "promote.py"
PROMOTE_SPEC = importlib.util.spec_from_file_location("model_promote", PROMOTE_PATH)
assert PROMOTE_SPEC is not None and PROMOTE_SPEC.loader is not None
sys.path.insert(0, str(REPOSITORY_ROOT))
try:
    promote = importlib.util.module_from_spec(PROMOTE_SPEC)
    PROMOTE_SPEC.loader.exec_module(promote)
finally:
    sys.path.remove(str(REPOSITORY_ROOT))


def _valid_params(**overrides):
    params = {
        "git_commit": "a" * 40,
        "dvc_data_hash": "b" * 32,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "target_schema_version": TARGET_SCHEMA_VERSION,
        "training_data_contract": TRAINING_DATA_CONTRACT,
        "registered_model_name": REGISTERED_MODEL_NAME,
        "forecast_horizons": "1,2,3",
        "target_score_names": "heat,rain",
        "target_columns": ",".join(TARGET_COLUMNS),
        "output_count": "6",
        "label_source": "open_meteo_era5",
        "supported_target_components": "heat,rain",
        "unsupported_target_components": "wind,air,river",
        "canonical_vintage_rule": (
            "latest_complete_weather_vintage_per_city_local_origin_date"
        ),
        "training_grain": "city_id,forecast_origin_date",
        "purge_gap_days": "4",
        "row_count": "200",
        "train_rows": "100",
        "test_rows": "80",
        "distinct_origin_dates": "20",
        "train_distinct_origin_dates": "10",
        "test_distinct_origin_dates": "8",
    }
    params.update(overrides)
    return params


def _valid_metrics(**overrides):
    metrics = {}
    for horizon in FORECAST_HORIZONS:
        metrics[f"r2_d{horizon}"] = 0.75
        metrics[f"mae_d{horizon}"] = 3.0
        for score_name in promote.SCORE_NAMES:
            metrics[f"r2_{score_name}_d{horizon}"] = 0.70
            metrics[f"mae_{score_name}_d{horizon}"] = 3.0
            metrics[f"test_count_{score_name}_d{horizon}"] = 80.0
            metrics[f"test_std_{score_name}_d{horizon}"] = 2.0
            metrics[f"test_nonzero_count_{score_name}_d{horizon}"] = 40.0
    metrics.update(overrides)
    return metrics


def _run(params=None, metrics=None):
    return SimpleNamespace(
        data=SimpleNamespace(
            params=params or _valid_params(),
            metrics=metrics or _valid_metrics(),
        )
    )


def _promotion_context(client, version="41"):
    return (
        patch.dict(
            "os.environ",
            {
                "DAGSHUB_USERNAME": "owner",
                "DAGSHUB_USER_TOKEN": "token",
                "MLFLOW_MODEL_VERSION": version,
                "MLFLOW_MODEL_ALIAS": "champion",
            },
            clear=False,
        ),
        patch.dict(
            "sys.modules",
            {"dagshub": SimpleNamespace(init=MagicMock())},
        ),
        patch.object(promote, "MlflowClient", return_value=client),
    )


def test_promotion_uses_exact_training_version_and_assigns_champion():
    client = MagicMock()
    client.get_model_version.return_value = SimpleNamespace(
        version="41",
        run_id="run-41",
        status="READY",
    )
    client.get_run.return_value = _run()
    contexts = _promotion_context(client)

    with contexts[0], contexts[1], contexts[2]:
        promote.promote_model()

    client.get_model_version.assert_called_once_with(REGISTERED_MODEL_NAME, "41")
    client.search_model_versions.assert_not_called()
    client.transition_model_version_stage.assert_called_once_with(
        name=REGISTERED_MODEL_NAME,
        version="41",
        stage="Production",
        archive_existing_versions=True,
    )
    client.set_registered_model_alias.assert_called_once_with(
        REGISTERED_MODEL_NAME,
        "champion",
        "41",
    )


@pytest.mark.parametrize(
    "params",
    (
        _valid_params(target_schema_version="legacy_proxy_targets"),
        _valid_params(supported_target_components="heat,wind,rain,air,river"),
        _valid_params(dvc_data_hash="unknown"),
    ),
    ids=("wrong-target-schema", "proxy-components", "missing-dvc-provenance"),
)
def test_promotion_rejects_wrong_contract_or_provenance(params):
    client = MagicMock()
    client.get_model_version.return_value = SimpleNamespace(
        version="42", run_id="run-42", status="READY"
    )
    client.get_run.return_value = _run(params=params)
    contexts = _promotion_context(client, version="42")

    with contexts[0], contexts[1], contexts[2], pytest.raises(SystemExit) as error:
        promote.promote_model()

    assert error.value.code == 1
    client.set_registered_model_alias.assert_not_called()


@pytest.mark.parametrize(
    "metric_override",
    (
        {"r2_d2": 0.20},
        {"mae_heat_score_d2": 10.01},
        {"test_count_rain_score_d3": 79.0},
        {"test_std_rain_score_d1": 0.0},
        {"test_nonzero_count_rain_score_d1": 1.0},
        {"r2_heat_score_d1": float("nan")},
    ),
    ids=(
        "horizon-quality",
        "component-quality",
        "support-count",
        "constant-target",
        "nonzero-support",
        "non-finite-metric",
    ),
)
def test_promotion_rejects_failed_quality_or_support_gate(metric_override):
    client = MagicMock()
    client.get_model_version.return_value = SimpleNamespace(
        version="43", run_id="run-43", status="READY"
    )
    client.get_run.return_value = _run(metrics=_valid_metrics(**metric_override))
    contexts = _promotion_context(client, version="43")

    with contexts[0], contexts[1], contexts[2], pytest.raises(SystemExit) as error:
        promote.promote_model()

    assert error.value.code == 1
    client.set_registered_model_alias.assert_not_called()


def test_promotion_rejects_insufficient_held_out_dates():
    client = MagicMock()
    client.get_model_version.return_value = SimpleNamespace(
        version="44", run_id="run-44", status="READY"
    )
    client.get_run.return_value = _run(
        params=_valid_params(
            distinct_origin_dates="20",
            train_distinct_origin_dates="14",
            test_distinct_origin_dates="5",
        )
    )
    contexts = _promotion_context(client, version="44")

    with contexts[0], contexts[1], contexts[2], pytest.raises(SystemExit) as error:
        promote.promote_model()

    assert error.value.code == 1
    client.transition_model_version_stage.assert_not_called()


def test_promotion_rejects_model_version_that_is_not_ready():
    client = MagicMock()
    client.get_model_version.return_value = SimpleNamespace(
        version="45", run_id="run-45", status="PENDING_REGISTRATION"
    )
    contexts = _promotion_context(client, version="45")

    with contexts[0], contexts[1], contexts[2], pytest.raises(SystemExit) as error:
        promote.promote_model()

    assert error.value.code == 1
    client.get_run.assert_not_called()
    client.transition_model_version_stage.assert_not_called()


@pytest.mark.parametrize(
    "workflow_name",
    ("ci-staging.yml", "ci-production.yml"),
)
def test_deployment_workflows_run_promoter_as_package(workflow_name):
    """Keep sibling backend/model packages importable in GitHub Actions."""
    workflow = (
        REPOSITORY_ROOT / ".github" / "workflows" / workflow_name
    ).read_text(encoding="utf-8")

    assert "run: python -m model.promote" in workflow
    assert "run: python model/promote.py" not in workflow
