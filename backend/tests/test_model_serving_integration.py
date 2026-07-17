"""Real local MLflow Registry-to-FastAPI model-serving integration test."""

from datetime import date
import math
from unittest.mock import MagicMock, patch
from uuid import uuid4

import mlflow
import mlflow.sklearn
from mlflow.models import infer_signature
from mlflow.tracking import MlflowClient
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import main
from app.ml_pipeline import (
    ALL_CITIES,
    FEATURE_COLUMNS,
    NUMERIC_FEATURE_COLUMNS,
    TARGET_COLUMNS,
    build_model_pipeline,
    prepare_feature_frame,
    validate_fitted_pipeline,
)


def _synthetic_training_data() -> pd.DataFrame:
    rng = np.random.default_rng(42)
    row_count = 40
    data = {
        column: rng.normal(loc=index + 20.0, scale=4.0, size=row_count)
        for index, column in enumerate(NUMERIC_FEATURE_COLUMNS)
    }
    data["city_id"] = [ALL_CITIES[index % len(ALL_CITIES)] for index in range(row_count)]
    frame = pd.DataFrame(data)
    for target_index, target in enumerate(TARGET_COLUMNS):
        signal = frame[NUMERIC_FEATURE_COLUMNS[target_index]]
        frame[target] = (
            signal * (0.8 + target_index * 0.1)
            + rng.normal(scale=2.0 + target_index, size=row_count)
        )
    return frame


def _register_real_pipeline(
    client: MlflowClient,
    experiment_id: str,
    model_name: str,
    training_data: pd.DataFrame,
    random_state: int,
) -> str:
    raw_features = prepare_feature_frame(training_data)
    targets = training_data.loc[:, list(TARGET_COLUMNS)]
    pipeline = build_model_pipeline(
        {
            "n_estimators": 5,
            "max_depth": 3,
            "random_state": random_state,
            "n_jobs": 1,
        }
    )
    pipeline.fit(raw_features, targets)

    input_example = raw_features.head(5).copy()
    output_example = pipeline.predict(input_example)
    signature = infer_signature(input_example, output_example)

    with mlflow.start_run(experiment_id=experiment_id):
        model_info = mlflow.sklearn.log_model(
            sk_model=pipeline,
            artifact_path="risk_forecaster",
            registered_model_name=model_name,
            signature=signature,
            input_example=input_example,
            await_registration_for=60,
            serialization_format=mlflow.sklearn.SERIALIZATION_FORMAT_CLOUDPICKLE,
        )

    version = str(model_info.registered_model_version)
    registered_version = client.get_model_version(model_name, version)
    assert registered_version.status == "READY"
    return version


def _feature_store_row(training_data: pd.DataFrame) -> dict:
    row = training_data.iloc[0].loc[list(FEATURE_COLUMNS)].to_dict()
    row.update(
        {
            "date": date(2026, 7, 17),
            "real_current_tipping_score": 61.0,
            "real_primary_driver": "Heat",
        }
    )
    return row


def _mock_bigquery_client(row: dict) -> MagicMock:
    query_job = MagicMock()
    query_job.result.return_value = [row]
    client = MagicMock()
    client.query.return_value = query_job
    return client


def _assert_finite_forecast(response_body: dict) -> None:
    assert set(response_body["sub_scores_forecast"]) == set(main.SUB_SCORE_NAMES)
    for forecast in response_body["sub_scores_forecast"].values():
        for field in ("estimated_score", "ci_lower", "ci_upper", "confidence_margin"):
            assert math.isfinite(forecast[field])
    assert math.isfinite(response_body["estimated_total_tipping_score"])
    assert 0.0 <= response_body["estimated_total_tipping_score"] <= 100.0


@pytest.mark.integration
def test_real_registry_alias_pin_and_missing_alias_serving(tmp_path, monkeypatch):
    original_tracking_uri = mlflow.get_tracking_uri()
    original_registry_uri = mlflow.get_registry_uri()
    original_cached_model = main._cached_model

    tracking_uri = f"sqlite:///{tmp_path / 'mlflow.db'}"
    artifact_root = (tmp_path / "artifacts").resolve()
    artifact_root.mkdir()
    model_name = f"ClimaSentinel_RiskForecaster_{uuid4().hex}"

    for variable in (
        "DAGSHUB_USER_TOKEN",
        "DAGSHUB_TOKEN",
        "DAGSHUB_USERNAME",
        "MLFLOW_MODEL_VERSION",
        "MLFLOW_MODEL_ALIAS",
    ):
        monkeypatch.delenv(variable, raising=False)

    monkeypatch.setattr(main, "MODEL_NAME", model_name)
    monkeypatch.setattr(main.settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(main.settings, "MLFLOW_MODEL_VERSION", None)
    monkeypatch.setattr(main.settings, "MLFLOW_MODEL_ALIAS", "champion")

    try:
        mlflow.set_tracking_uri(tracking_uri)
        mlflow.set_registry_uri(tracking_uri)
        registry_client = MlflowClient()
        experiment_id = registry_client.create_experiment(
            f"model-serving-integration-{uuid4().hex}",
            artifact_location=artifact_root.as_uri(),
        )

        training_data = _synthetic_training_data()
        version_1 = _register_real_pipeline(
            registry_client,
            experiment_id,
            model_name,
            training_data,
            random_state=42,
        )
        registry_client.set_registered_model_alias(
            model_name,
            "champion",
            version_1,
        )
        version_2 = _register_real_pipeline(
            registry_client,
            experiment_id,
            model_name,
            training_data,
            random_state=99,
        )

        assert version_1 == "1"
        assert version_2 == "2"
        assert str(
            registry_client.get_model_version_by_alias(
                model_name,
                "champion",
            ).version
        ) == version_1

        bq_client = _mock_bigquery_client(_feature_store_row(training_data))
        api_client = TestClient(main.app)
        main._cached_model = None

        with (
            patch("app.main.get_bq_client", return_value=bq_client),
            patch("app.main._heuristic_predictions") as fallback,
        ):
            champion_response = api_client.get(
                "/data/city/paris_fr/forecast?horizon_days=3"
            )
            assert champion_response.status_code == 200
            champion_body = champion_response.json()
            assert champion_body["prediction_source"] == "mlflow_registry"
            assert champion_body["model_version"] == version_1
            assert champion_body["model_version"] != version_2
            _assert_finite_forecast(champion_body)
            fallback.assert_not_called()

            assert main._cached_model is not None
            assert main._cached_model.model_version == version_1
            validate_fitted_pipeline(main._cached_model.estimator)

            # A changed alias configuration cannot move the concrete cached version.
            main.settings.MLFLOW_MODEL_ALIAS = "alias-that-does-not-exist"
            cached_response = api_client.get(
                "/data/city/paris_fr/forecast?horizon_days=3"
            )
            assert cached_response.status_code == 200
            assert cached_response.json()["model_version"] == version_1
            fallback.assert_not_called()

            # An explicit pin overrides champion and serves the newer version.
            main.settings.MLFLOW_MODEL_ALIAS = "champion"
            main.settings.MLFLOW_MODEL_VERSION = version_2
            main._cached_model = None
            pinned_response = api_client.get(
                "/data/city/paris_fr/forecast?horizon_days=3"
            )
            assert pinned_response.status_code == 200
            assert pinned_response.json()["prediction_source"] == "mlflow_registry"
            assert pinned_response.json()["model_version"] == version_2
            assert str(
                registry_client.get_model_version_by_alias(
                    model_name,
                    "champion",
                ).version
            ) == version_1
            fallback.assert_not_called()

            # A missing alias fails closed in production instead of serving latest.
            main.settings.MLFLOW_MODEL_VERSION = None
            main.settings.MLFLOW_MODEL_ALIAS = "alias-that-does-not-exist"
            main._cached_model = None
            missing_alias_response = api_client.get(
                "/data/city/paris_fr/forecast?horizon_days=3"
            )
            assert missing_alias_response.status_code == 503
            assert missing_alias_response.json() == {
                "detail": "ML forecast model is temporarily unavailable"
            }
            fallback.assert_not_called()
    finally:
        main._cached_model = original_cached_model
        mlflow.set_tracking_uri(original_tracking_uri)
        mlflow.set_registry_uri(original_registry_uri)
