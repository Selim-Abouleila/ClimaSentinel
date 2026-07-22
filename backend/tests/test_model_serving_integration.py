"""Integration checks for registry-independent rule-baseline serving."""

from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
import pytest

from app import main


def _serving_feature_row() -> dict:
    row = {
        "city_id": "paris_fr",
        "forecast_origin_date": date(2026, 7, 31),
        "forecast_origin_time_zone": "Europe/Paris",
        "ingestion_run_id": "integration-run",
        "ingested_at_utc": datetime(2026, 7, 31, 5, tzinfo=timezone.utc),
        "forecast_age_days": 0,
        "is_canonical_daily_vintage": True,
        "has_expected_horizon_dates": True,
        "has_complete_weather_feature_window": True,
        "current_tipping_score": 61.0,
        # This is July's normal and must not be used for the August target.
        "normal_temperature_2m_max": 28.0,
        "target_normal_temperature_2m_max": 26.0,
    }
    for horizon in range(1, 5):
        row[f"temp_forecast_plus_{horizon}d"] = 29.0 + horizon
        row[f"weather_has_24_hour_coverage_plus_{horizon}d"] = True
        row[f"has_complete_weather_values_plus_{horizon}d"] = True
        row[f"has_air_quality_forecast_plus_{horizon}d"] = True
        row[f"air_quality_has_24_hour_coverage_plus_{horizon}d"] = True
        row[f"has_complete_air_quality_values_plus_{horizon}d"] = True
        row[f"has_flood_forecast_plus_{horizon}d"] = True
        row[f"wind_gusts_forecast_plus_{horizon}d"] = 50.0
        row[f"aqi_forecast_plus_{horizon}d"] = 45.0
        row[f"river_forecast_plus_{horizon}d"] = 40.0
        if horizon <= 3:
            row[f"precip_forecast_plus_{horizon}d"] = float(horizon)
            row[f"wind_forecast_plus_{horizon}d"] = 12.0
    return row


def _mock_bigquery_client(row: dict) -> MagicMock:
    query_job = MagicMock()
    query_job.result.return_value = [row]
    client = MagicMock()
    client.query.return_value = query_job
    return client


@pytest.mark.integration
@pytest.mark.parametrize("environment", ["staging", "production"])
def test_deployed_rule_policy_never_resolves_or_loads_registry_model(environment):
    """A missing or broken champion cannot block the operational baseline."""
    row = _serving_feature_row()
    bq_client = _mock_bigquery_client(row)

    with (
        patch("app.main.get_bq_client", return_value=bq_client),
        patch("mlflow.sklearn.load_model") as load_model,
        patch("mlflow.tracking.MlflowClient") as mlflow_client,
        patch.object(main.settings, "ENVIRONMENT", environment),
        patch.dict(
            "os.environ",
            {
                "MLFLOW_MODEL_ALIAS": "missing-champion",
                "MLFLOW_MODEL_VERSION": "999999",
            },
            clear=False,
        ),
    ):
        response = TestClient(main.app).get(
            "/data/city/paris_fr/forecast?horizon_days=1"
        )

    assert response.status_code == 200
    body = response.json()
    assert body["prediction_source"] == "same_vintage_forecast_rules"
    assert body["forecast_method"] == "forecast_rules_baseline"
    assert body["model_version"] is None
    assert body["model_target_components"] == []
    assert body["sub_scores_forecast"]["heat_score"]["estimated_score"] == 25.0
    assert body["sub_scores_forecast"]["rain_score"]["estimated_score"] == 2.0
    load_model.assert_not_called()
    mlflow_client.assert_not_called()


@pytest.mark.integration
def test_rule_response_contains_no_synthetic_model_intervals():
    row = _serving_feature_row()

    with patch(
        "app.main.get_bq_client",
        return_value=_mock_bigquery_client(row),
    ):
        response = TestClient(main.app).get(
            "/data/city/paris_fr/forecast?horizon_days=3"
        )

    assert response.status_code == 200
    body = response.json()
    assert body["total_confidence_margin"] is None
    assert body["total_ci_lower"] is None
    assert body["total_ci_upper"] is None
    assert body["total_uncertainty_method"] == "none"
    for component in body["sub_scores_forecast"].values():
        assert component["ci_lower"] is None
        assert component["ci_upper"] is None
        assert component["confidence_margin"] is None
        assert component["uncertainty_method"] == "none"
