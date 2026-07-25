"""Focused offline tests for shared training and forecast inference behavior."""

from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

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
    chronological_purged_split,
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


def _mock_serving_feature_row(frame: pd.DataFrame) -> dict:
    row = frame.iloc[0].loc[list(FEATURE_COLUMNS)].to_dict()
    row.update(
        {
            "city_id": "paris_fr",
            "forecast_origin_date": date(2026, 7, 17),
            "forecast_origin_time_zone": "Europe/Paris",
            "ingestion_run_id": "run-2026-07-17",
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


def test_shared_pipeline_fits_and_predicts_raw_features(synthetic_training_data):
    model = _fit_tiny_pipeline(synthetic_training_data)

    predictions = model.predict(
        synthetic_training_data.loc[:5, list(FEATURE_COLUMNS)]
    )

    assert predictions.shape == (6, 6)
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


def test_pipeline_preserves_nullable_optional_feature_contract(
    synthetic_training_data,
):
    nullable = synthetic_training_data.copy()
    nullable.loc[::2, "european_aqi_max"] = None
    nullable.loc[1::2, "river_forecast_plus_3d"] = None

    model = _fit_tiny_pipeline(nullable)
    predictions = model.predict(
        nullable.loc[:3, list(FEATURE_COLUMNS)]
    )

    assert predictions.shape == (4, 6)
    assert np.isfinite(predictions).all()


def test_artifact_without_embedded_semantic_contract_is_rejected(
    synthetic_training_data,
):
    model = _fit_tiny_pipeline(synthetic_training_data)
    del model.climasentinel_target_schema_version

    with pytest.raises(ValueError, match="contract field"):
        predict_with_ensemble_spread(
            model,
            synthetic_training_data.loc[:1, list(FEATURE_COLUMNS)],
        )


def test_chronological_split_groups_dates_and_purges_target_overlap():
    dates = pd.Series(
        np.repeat(pd.date_range("2026-01-01", periods=10, freq="D"), 2)
    )
    features = pd.DataFrame({"date_marker": dates, "value": np.arange(len(dates))})
    targets = pd.DataFrame({"target": np.arange(len(dates), dtype=float)})

    X_train, X_test, y_train, y_test, test_start = chronological_purged_split(
        features,
        targets,
        dates,
    )

    assert test_start == pd.Timestamp("2026-01-09")
    assert X_train["date_marker"].max() == pd.Timestamp("2026-01-04")
    assert X_test["date_marker"].min() == test_start
    assert len(X_train) == len(y_train) == 8
    assert len(X_test) == len(y_test) == 4


def test_multioutput_tree_traversal_returns_per_output_spread(
    synthetic_training_data,
):
    model = _fit_tiny_pipeline(synthetic_training_data)
    prediction_rows = synthetic_training_data.loc[:7, list(FEATURE_COLUMNS)]

    predictions, spread = predict_with_ensemble_spread(model, prediction_rows)

    assert predictions.shape == (8, 6)
    assert spread.shape == (8, 6)
    assert np.isfinite(predictions).all()
    assert np.isfinite(spread).all()
    assert not np.allclose(spread, spread[0, 0])


@pytest.mark.parametrize("horizon_days", FORECAST_HORIZONS)
def test_shared_pipeline_returns_only_requested_horizon_outputs(
    synthetic_training_data,
    horizon_days,
):
    model = _fit_tiny_pipeline(synthetic_training_data)

    predictions, spread = predict_with_ensemble_spread(
        model,
        synthetic_training_data.loc[:5, list(FEATURE_COLUMNS)],
        horizon_days=horizon_days,
    )

    assert predictions.shape == (6, 2)
    assert spread.shape == (6, 2)
    assert np.isfinite(predictions).all()
    assert np.isfinite(spread).all()


def test_horizon_specific_targets_are_distinct(synthetic_training_data):
    model = _fit_tiny_pipeline(synthetic_training_data)
    features = synthetic_training_data.loc[:5, list(FEATURE_COLUMNS)]

    horizon_means = [
        predict_with_ensemble_spread(
            model,
            features,
            horizon_days=horizon,
        )[0].mean()
        for horizon in FORECAST_HORIZONS
    ]

    assert horizon_means[0] < horizon_means[1] < horizon_means[2]


def test_invalid_prediction_horizon_is_rejected(synthetic_training_data):
    model = _fit_tiny_pipeline(synthetic_training_data)

    with pytest.raises(ValueError, match="Unsupported forecast horizon"):
        predict_with_ensemble_spread(
            model,
            synthetic_training_data.loc[:1, list(FEATURE_COLUMNS)],
            horizon_days=4,
        )


def test_legacy_day_three_only_artifact_is_rejected(synthetic_training_data):
    legacy_model = build_model_pipeline(
        {
            "n_estimators": 3,
            "max_depth": 2,
            "random_state": 42,
            "n_jobs": 1,
        }
    )
    legacy_model.fit(
        prepare_feature_frame(synthetic_training_data),
        synthetic_training_data.loc[
            :,
            list(TARGET_COLUMNS_BY_HORIZON[3]),
        ],
    )

    with pytest.raises(ValueError, match="expected 6 fitted output estimators"):
        predict_with_ensemble_spread(
            legacy_model,
            synthetic_training_data.loc[:1, list(FEATURE_COLUMNS)],
            horizon_days=3,
        )


@pytest.mark.parametrize("environment", ["development", "staging", "production"])
@pytest.mark.parametrize("horizon_days", FORECAST_HORIZONS)
def test_endpoint_serves_explicit_rules_without_a_registry_model(
    synthetic_training_data,
    environment,
    horizon_days,
):
    row = _mock_serving_feature_row(synthetic_training_data)
    row["target_normal_temperature_2m_max"] = 25.0
    bq_client = _mock_bigquery_client(row)

    with (
        patch("app.main.get_bq_client", return_value=bq_client),
        patch.object(main.settings, "ENVIRONMENT", environment),
    ):
        response = TestClient(main.app).get(
            f"/data/city/paris_fr/forecast?horizon_days={horizon_days}"
        )

    assert response.status_code == 200
    body = response.json()
    assert body["horizon_days"] == horizon_days
    assert body["prediction_source"] == "same_vintage_forecast_rules"
    assert body["forecast_method"] == "forecast_rules_baseline"
    assert body["model_version"] is None
    assert body["model_target_components"] == []
    assert body["rule_based_components"] == [
        "heat",
        "wind",
        "rain",
        "air",
        "river",
    ]
    assert body["feature_ingestion_run_id"] == "run-2026-07-17"

    components = body["sub_scores_forecast"]
    assert list(components) == list(main.SUB_SCORE_NAMES)
    for component in components.values():
        assert component["method"] == "forecast_rule"
        assert component["ci_lower"] is None
        assert component["ci_upper"] is None
        assert component["confidence_margin"] is None
        assert component["uncertainty_method"] == "none"
        assert component["provenance"]
        assert component["method_reason"]
    assert components["heat_score"]["validation_status"] == (
        "era5_backtested_limited"
    )
    assert components["rain_score"]["validation_status"] == (
        "era5_backtested_insufficient_skill"
    )
    for name in ("wind_score", "air_score", "river_score"):
        assert components[name]["validation_status"] == (
            "not_observation_validated"
        )

    submitted_query = bq_client.query.call_args.args[0]
    assert "mart_ml_serving_features_current" in submitted_query
    assert (
        f"`{main.settings.GCP_PROJECT_ID}."
        f"{main.settings.BQ_STAGING_DATASET}.city_monthly_normals`"
        in submitted_query
    )
    assert "target_normal_temperature_2m_max" in submitted_query
    assert "mart_ml_feature_store" not in submitted_query
    query_parameters = {
        parameter.name: parameter.value
        for parameter in bq_client.query.call_args.kwargs[
            "job_config"
        ].query_parameters
    }
    assert query_parameters == {
        "city_id": "paris_fr",
        "horizon_days": horizon_days,
    }


def test_endpoint_uses_target_month_normal_for_heat(synthetic_training_data):
    row = _mock_serving_feature_row(synthetic_training_data)
    row.update(
        {
            "normal_temperature_2m_max": -50.0,
            "target_normal_temperature_2m_max": 25.0,
            "temp_forecast_plus_1d": 30.0,
            "temp_forecast_plus_2d": 32.0,
            "precip_forecast_plus_1d": 1.5,
        }
    )

    with patch(
        "app.main.get_bq_client",
        return_value=_mock_bigquery_client(row),
    ):
        response = TestClient(main.app).get(
            "/data/city/paris_fr/forecast?horizon_days=1"
        )

    assert response.status_code == 200
    components = response.json()["sub_scores_forecast"]
    assert components["heat_score"]["estimated_score"] == 35.0
    assert components["rain_score"]["estimated_score"] == 3.0


def test_missing_optional_sources_remain_unavailable_in_endpoint(
    synthetic_training_data,
):
    row = _mock_serving_feature_row(synthetic_training_data)
    row["target_normal_temperature_2m_max"] = 25.0
    row["has_air_quality_forecast_plus_2d"] = False
    row["aqi_forecast_plus_2d"] = None
    row["has_flood_forecast_plus_2d"] = False
    row["river_forecast_plus_2d"] = None

    with patch(
        "app.main.get_bq_client",
        return_value=_mock_bigquery_client(row),
    ):
        response = TestClient(main.app).get(
            "/data/city/paris_fr/forecast?horizon_days=2"
        )

    assert response.status_code == 200
    components = response.json()["sub_scores_forecast"]
    for name in ("air_score", "river_score"):
        assert components[name]["available"] is False
        assert components[name]["estimated_score"] is None
        assert components[name]["unavailable_reason"]
    assert components["heat_score"]["available"] is True
    assert components["rain_score"]["available"] is True


def test_rule_driver_never_reports_a_model_uncertainty_band(
    synthetic_training_data,
):
    row = _mock_serving_feature_row(synthetic_training_data)
    row["target_normal_temperature_2m_max"] = 25.0
    row["wind_gusts_forecast_plus_1d"] = 80.0

    with patch(
        "app.main.get_bq_client",
        return_value=_mock_bigquery_client(row),
    ):
        response = TestClient(main.app).get(
            "/data/city/paris_fr/forecast?horizon_days=1"
        )

    assert response.status_code == 200
    body = response.json()
    assert body["forecast_primary_driver"] == "Wind"
    assert body["forecast_primary_driver_method"] == "forecast_rule"
    assert body["estimated_total_tipping_score"] == 100.0
    assert body["total_confidence_margin"] is None
    assert body["total_ci_lower"] is None
    assert body["total_ci_upper"] is None
    assert body["total_uncertainty_method"] == "none"
