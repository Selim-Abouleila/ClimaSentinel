"""Real local MLflow Registry-to-FastAPI model-serving integration test."""

from datetime import date, datetime, timezone
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
    FORECAST_HORIZONS,
    NUMERIC_FEATURE_COLUMNS,
    TARGET_COLUMNS,
    TARGET_COLUMNS_BY_HORIZON,
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
    for horizon in FORECAST_HORIZONS:
        for target_index, target in enumerate(
            TARGET_COLUMNS_BY_HORIZON[horizon]
        ):
            signal = frame[NUMERIC_FEATURE_COLUMNS[target_index]]
            frame[target] = (
                horizon * 20.0
                + signal * (0.10 + target_index * 0.02)
                + rng.normal(scale=0.5, size=row_count)
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
            name="risk_forecaster",
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


def _serving_feature_row(training_data: pd.DataFrame) -> dict:
    row = training_data.iloc[0].loc[list(FEATURE_COLUMNS)].to_dict()
    row.update(
        {
            "city_id": "paris_fr",
            "forecast_origin_date": date(2026, 7, 17),
            "forecast_origin_time_zone": "Europe/Paris",
            "ingestion_run_id": "integration-run",
            "ingested_at_utc": datetime(2026, 7, 17, 5, tzinfo=timezone.utc),
            "forecast_age_days": 0,
            "is_canonical_daily_vintage": True,
            "has_expected_horizon_dates": True,
            "has_complete_weather_feature_window": True,
            "current_tipping_score": 61.0,
        }
    )
    for horizon in range(1, 5):
        row[f"weather_has_24_hour_coverage_plus_{horizon}d"] = True
        row[f"has_complete_weather_values_plus_{horizon}d"] = True
        row[f"has_air_quality_forecast_plus_{horizon}d"] = True
        row[f"air_quality_has_24_hour_coverage_plus_{horizon}d"] = True
        row[f"has_complete_air_quality_values_plus_{horizon}d"] = True
        row[f"has_flood_forecast_plus_{horizon}d"] = True
    return row


def _mock_bigquery_client(row: dict) -> MagicMock:
    query_job = MagicMock()
    query_job.result.return_value = [row]
    client = MagicMock()
    client.query.return_value = query_job
    return client


def _assert_finite_forecast(response_body: dict) -> None:
    assert set(response_body["sub_scores_forecast"]) == set(main.SUB_SCORE_NAMES)
    for name in ("heat_score", "rain_score"):
        forecast = response_body["sub_scores_forecast"][name]
        for field in ("estimated_score", "ci_lower", "ci_upper", "confidence_margin"):
            assert math.isfinite(forecast[field])
        assert forecast["method"] == "learned_model"
        assert forecast["uncertainty_method"] == "tree_spread_not_calibrated"
    for name in ("wind_score", "air_score", "river_score"):
        forecast = response_body["sub_scores_forecast"][name]
        assert forecast["method"] == "forecast_rule"
        assert forecast["validation_status"] == "not_observation_validated"
        assert forecast["ci_lower"] is None
        assert forecast["ci_upper"] is None
        assert forecast["confidence_margin"] is None
    assert math.isfinite(response_body["estimated_total_tipping_score"])
    assert 0.0 <= response_body["estimated_total_tipping_score"] <= 100.0
    assert response_body["forecast_method"] == "hybrid_ml_and_forecast_rules"


@pytest.mark.integration
def test_real_registry_alias_pin_and_missing_alias_serving(tmp_path, monkeypatch):
    original_tracking_uri = mlflow.get_tracking_uri()
    original_registry_uri = mlflow.get_registry_uri()
    original_cached_model = main._cached_model

    tracking_uri = f"sqlite:///{tmp_path / 'mlflow.db'}"
    artifact_root = (tmp_path / "artifacts").resolve()
    artifact_root.mkdir()
    model_name = f"ClimaSentinel_HeatRainForecaster_{uuid4().hex}"

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

        bq_client = _mock_bigquery_client(_serving_feature_row(training_data))
        api_client = TestClient(main.app)
        main._cached_model = None

        with (
            patch("app.main.get_bq_client", return_value=bq_client),
            patch("app.main._development_heat_rain_estimates") as fallback,
        ):
            champion_responses = [
                api_client.get(
                    f"/data/city/paris_fr/forecast?horizon_days={horizon}"
                )
                for horizon in FORECAST_HORIZONS
            ]
            assert all(response.status_code == 200 for response in champion_responses)
            champion_bodies = [response.json() for response in champion_responses]
            assert [
                body["horizon_days"] for body in champion_bodies
            ] == list(FORECAST_HORIZONS)
            assert all(
                body["prediction_source"] == "mlflow_registry"
                for body in champion_bodies
            )
            assert all(
                body["model_version"] == version_1
                for body in champion_bodies
            )
            assert all(
                body["model_version"] != version_2
                for body in champion_bodies
            )
            assert (
                champion_bodies[0]["estimated_total_tipping_score"]
                < champion_bodies[1]["estimated_total_tipping_score"]
                < champion_bodies[2]["estimated_total_tipping_score"]
            )
            for champion_body in champion_bodies:
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
