"""Focused offline tests for shared training and forecast inference behavior."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

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
    predict_with_ensemble_spread,
    prepare_feature_frame,
)


@pytest.fixture
def synthetic_training_data() -> pd.DataFrame:
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


def _fit_tiny_pipeline(frame: pd.DataFrame):
    model = build_model_pipeline(
        {
            "n_estimators": 7,
            "max_depth": 4,
            "random_state": 42,
            "n_jobs": 1,
        }
    )
    model.fit(
        prepare_feature_frame(frame),
        frame.loc[:, list(TARGET_COLUMNS)],
    )
    return model


def _mock_feature_store_row(frame: pd.DataFrame) -> dict:
    row = frame.iloc[0].loc[list(FEATURE_COLUMNS)].to_dict()
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


def test_shared_pipeline_fits_and_predicts_raw_features(synthetic_training_data):
    model = _fit_tiny_pipeline(synthetic_training_data)

    predictions = model.predict(
        synthetic_training_data.loc[:5, list(FEATURE_COLUMNS)]
    )

    assert predictions.shape == (6, 5)
    assert np.isfinite(predictions).all()


def test_prepare_feature_frame_restores_authoritative_order(synthetic_training_data):
    shuffled = synthetic_training_data.loc[:, list(FEATURE_COLUMNS)].sample(
        frac=1,
        axis=1,
        random_state=42,
    )

    prepared = prepare_feature_frame(shuffled)

    assert list(prepared.columns) == list(FEATURE_COLUMNS)


def test_prepare_feature_frame_identifies_missing_column(synthetic_training_data):
    incomplete = synthetic_training_data.drop(columns=["aqi_forecast_plus_2d"])

    with pytest.raises(ValueError, match="aqi_forecast_plus_2d"):
        prepare_feature_frame(incomplete)


def test_multioutput_tree_traversal_returns_per_output_spread(
    synthetic_training_data,
):
    model = _fit_tiny_pipeline(synthetic_training_data)
    prediction_rows = synthetic_training_data.loc[:7, list(FEATURE_COLUMNS)]

    predictions, spread = predict_with_ensemble_spread(model, prediction_rows)

    assert predictions.shape == (8, 5)
    assert spread.shape == (8, 5)
    assert np.isfinite(predictions).all()
    assert np.isfinite(spread).all()
    assert not np.allclose(spread, spread[0, 0])


def test_production_model_failure_returns_503_without_fallback(
    synthetic_training_data,
):
    row = _mock_feature_store_row(synthetic_training_data)
    bq_client = _mock_bigquery_client(row)

    with (
        patch("app.main.get_bq_client", return_value=bq_client),
        patch("app.main._get_ml_model", return_value=None),
        patch("app.main._heuristic_predictions") as fallback,
        patch.object(main.settings, "ENVIRONMENT", " production "),
    ):
        response = TestClient(main.app).get("/data/city/paris_fr/forecast")

    assert response.status_code == 503
    assert response.json() == {
        "detail": "ML forecast model is temporarily unavailable"
    }
    fallback.assert_not_called()


def test_non_production_fallback_reports_provenance(synthetic_training_data):
    row = _mock_feature_store_row(synthetic_training_data)
    bq_client = _mock_bigquery_client(row)

    with (
        patch("app.main.get_bq_client", return_value=bq_client),
        patch("app.main._get_ml_model", return_value=None),
        patch.object(main.settings, "ENVIRONMENT", "staging"),
    ):
        response = TestClient(main.app).get("/data/city/paris_fr/forecast")

    assert response.status_code == 200
    body = response.json()
    assert body["prediction_source"] == "heuristic_fallback"
    assert body["model_version"] is None


def test_registry_alias_resolves_to_exact_version_without_latest_apis():
    client = MagicMock()
    client.get_model_version_by_alias.return_value = SimpleNamespace(
        version="7",
        status="READY",
    )

    with (
        patch.object(main.settings, "MLFLOW_MODEL_VERSION", None),
        patch.object(main.settings, "MLFLOW_MODEL_ALIAS", "champion"),
    ):
        reference = main._resolve_registry_model_reference(client)

    assert reference == main.ResolvedModelReference(
        model_uri="models:/ClimaSentinel_RiskForecaster/7",
        model_version="7",
        model_alias="champion",
    )
    client.get_model_version_by_alias.assert_called_once_with(
        "ClimaSentinel_RiskForecaster",
        "champion",
    )
    client.search_model_versions.assert_not_called()
    client.get_latest_versions.assert_not_called()


def test_explicit_version_pin_overrides_alias():
    client = MagicMock()
    client.get_model_version.return_value = SimpleNamespace(
        version="8",
        status="READY",
    )

    with (
        patch.object(main.settings, "MLFLOW_MODEL_VERSION", " 8 "),
        patch.object(main.settings, "MLFLOW_MODEL_ALIAS", "champion"),
    ):
        reference = main._resolve_registry_model_reference(client)

    assert reference == main.ResolvedModelReference(
        model_uri="models:/ClimaSentinel_RiskForecaster/8",
        model_version="8",
        model_alias=None,
    )
    client.get_model_version.assert_called_once_with(
        "ClimaSentinel_RiskForecaster",
        "8",
    )
    client.get_model_version_by_alias.assert_not_called()
    client.search_model_versions.assert_not_called()
    client.get_latest_versions.assert_not_called()


@pytest.mark.parametrize("configured_version", ["not-a-number", "0", "-1"])
def test_invalid_explicit_version_pin_is_rejected(configured_version):
    client = MagicMock()

    with (
        patch.object(main.settings, "MLFLOW_MODEL_VERSION", configured_version),
        pytest.raises(ValueError, match="positive integer string"),
    ):
        main._resolve_registry_model_reference(client)

    client.get_model_version.assert_not_called()
    client.get_model_version_by_alias.assert_not_called()


def test_blank_version_pin_uses_configured_alias():
    client = MagicMock()
    client.get_model_version_by_alias.return_value = SimpleNamespace(
        version="9",
        status="READY",
    )

    with (
        patch.object(main.settings, "MLFLOW_MODEL_VERSION", "   "),
        patch.object(main.settings, "MLFLOW_MODEL_ALIAS", "candidate-approved"),
    ):
        reference = main._resolve_registry_model_reference(client)

    assert reference.model_version == "9"
    assert reference.model_alias == "candidate-approved"
    client.get_model_version_by_alias.assert_called_once_with(
        "ClimaSentinel_RiskForecaster",
        "candidate-approved",
    )


def test_blank_alias_defaults_to_champion():
    client = MagicMock()
    client.get_model_version_by_alias.return_value = SimpleNamespace(
        version="10",
        status="READY",
    )

    with (
        patch.object(main.settings, "MLFLOW_MODEL_VERSION", None),
        patch.object(main.settings, "MLFLOW_MODEL_ALIAS", "  "),
    ):
        reference = main._resolve_registry_model_reference(client)

    assert reference.model_alias == "champion"
    client.get_model_version_by_alias.assert_called_once_with(
        "ClimaSentinel_RiskForecaster",
        "champion",
    )


def test_missing_alias_raises_clear_compatibility_error():
    client = MagicMock()
    client.get_model_version_by_alias.side_effect = RuntimeError("missing alias")

    with (
        patch.object(main.settings, "MLFLOW_MODEL_VERSION", None),
        patch.object(main.settings, "MLFLOW_MODEL_ALIAS", "missing"),
        pytest.raises(ValueError, match="Registry alias 'missing' could not be resolved"),
    ):
        main._resolve_registry_model_reference(client)

    client.search_model_versions.assert_not_called()
    client.get_latest_versions.assert_not_called()


def test_successful_ml_forecast_reports_loaded_model_provenance(
    synthetic_training_data,
):
    row = _mock_feature_store_row(synthetic_training_data)
    bq_client = _mock_bigquery_client(row)
    loaded_model = main.LoadedModel(
        estimator=_fit_tiny_pipeline(synthetic_training_data),
        prediction_source="mlflow_registry",
        model_version="18",
    )

    with (
        patch("app.main.get_bq_client", return_value=bq_client),
        patch("app.main._get_ml_model", return_value=loaded_model),
        patch("app.main._heuristic_predictions") as fallback,
        patch.object(main.settings, "ENVIRONMENT", "production"),
    ):
        response = TestClient(main.app).get("/data/city/paris_fr/forecast")

    assert response.status_code == 200
    body = response.json()
    assert body["prediction_source"] == "mlflow_registry"
    assert body["model_version"] == "18"
    fallback.assert_not_called()
