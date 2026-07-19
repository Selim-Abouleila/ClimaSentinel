"""Deterministic rule tests for the explicit operational baseline."""

import pytest
from pydantic import ValidationError

from app.forecast_rules import forecast_rule_estimates
from app.schemas import CityForecastResponse, ComponentForecast


def _complete_row() -> dict:
    row = {
        # Deliberately different: serving must use the target-month normal.
        "normal_temperature_2m_max": -99.0,
        "target_normal_temperature_2m_max": 25.0,
    }
    for horizon in range(1, 5):
        row[f"weather_has_24_hour_coverage_plus_{horizon}d"] = True
        row[f"has_complete_weather_values_plus_{horizon}d"] = True
        row[f"has_air_quality_forecast_plus_{horizon}d"] = True
        row[f"air_quality_has_24_hour_coverage_plus_{horizon}d"] = True
        row[f"has_complete_air_quality_values_plus_{horizon}d"] = True
        row[f"has_flood_forecast_plus_{horizon}d"] = True
        row[f"wind_gusts_forecast_plus_{horizon}d"] = 52.0
        row[f"temp_forecast_plus_{horizon}d"] = 29.0 + horizon
        if horizon <= 3:
            row[f"precip_forecast_plus_{horizon}d"] = 1.5 * horizon
        row[f"aqi_forecast_plus_{horizon}d"] = 70.0
        row[f"river_forecast_plus_{horizon}d"] = 60.0 + horizon * 6.0
    return row


@pytest.mark.parametrize("horizon", [1, 2, 3])
def test_rules_use_requested_same_vintage_horizon(horizon):
    row = _complete_row()

    estimates = forecast_rule_estimates(row, horizon)

    expected_heat = (
        row[f"temp_forecast_plus_{horizon}d"]
        - row["target_normal_temperature_2m_max"]
    ) * 5.0 + max(
        0.0,
        row[f"temp_forecast_plus_{horizon + 1}d"]
        - row[f"temp_forecast_plus_{horizon}d"],
    ) * 5.0
    assert estimates["heat_score"].score == expected_heat
    assert estimates["heat_score"].validation_status == "era5_backtested_limited"
    assert estimates["rain_score"].score == 3.0 * horizon
    assert (
        estimates["rain_score"].validation_status
        == "era5_backtested_insufficient_skill"
    )
    assert estimates["wind_score"].score == 30.0
    assert estimates["air_score"].score == 50.1
    expected_velocity = (
        row[f"river_forecast_plus_{horizon + 1}d"]
        - row[f"river_forecast_plus_{horizon}d"]
    ) / row[f"river_forecast_plus_{horizon}d"]
    assert estimates["river_score"].score == round(expected_velocity * 200.0, 1)


def test_day_three_river_velocity_requires_day_four_from_same_vintage():
    row = _complete_row()
    row["has_flood_forecast_plus_4d"] = False

    estimate = forecast_rule_estimates(row, 3)["river_score"]

    assert not estimate.available
    assert estimate.score is None
    assert "Next-day" in estimate.unavailable_reason


def test_day_three_heat_velocity_requires_day_four_from_same_vintage():
    row = _complete_row()
    row["has_complete_weather_values_plus_4d"] = False

    estimates = forecast_rule_estimates(row, 3)

    assert not estimates["heat_score"].available
    assert estimates["heat_score"].score is None
    assert "next-day" in estimates["heat_score"].unavailable_reason
    # Rain needs only the selected target day, not the following day.
    assert estimates["rain_score"].available


def test_heat_never_silently_uses_origin_month_normal():
    row = _complete_row()
    row["target_normal_temperature_2m_max"] = None

    estimates = forecast_rule_estimates(row, 1)

    assert estimates["heat_score"].score is None
    assert "target-month climatology" in estimates["heat_score"].unavailable_reason
    assert estimates["rain_score"].available


def test_below_threshold_river_is_zero_without_next_day_value():
    row = _complete_row()
    row["river_forecast_plus_2d"] = 50.0
    row["river_forecast_plus_3d"] = None
    row["has_flood_forecast_plus_3d"] = False

    estimate = forecast_rule_estimates(row, 2)["river_score"]

    assert estimate.available
    assert estimate.score == 0.0


def test_missing_sources_are_unavailable_not_zero():
    row = _complete_row()
    row["has_complete_weather_values_plus_1d"] = False
    row["has_air_quality_forecast_plus_1d"] = False
    row["has_flood_forecast_plus_1d"] = False

    estimates = forecast_rule_estimates(row, 1)

    for estimate in estimates.values():
        assert not estimate.available
        assert estimate.score is None
        assert estimate.unavailable_reason


def test_rules_clip_scores_to_operational_range():
    row = _complete_row()
    row["wind_gusts_forecast_plus_1d"] = 500.0
    row["aqi_forecast_plus_1d"] = -50.0
    row["river_forecast_plus_1d"] = 60.0
    row["river_forecast_plus_2d"] = 600.0
    row["temp_forecast_plus_1d"] = 100.0
    row["temp_forecast_plus_2d"] = 200.0
    row["precip_forecast_plus_1d"] = 500.0

    estimates = forecast_rule_estimates(row, 1)

    assert estimates["heat_score"].score == 100.0
    assert estimates["rain_score"].score == 100.0
    assert estimates["wind_score"].score == 100.0
    assert estimates["air_score"].score == 0.0
    assert estimates["river_score"].score == 100.0


def test_all_rules_expose_policy_provenance_and_reason():
    estimates = forecast_rule_estimates(_complete_row(), 2)

    assert set(estimates) == {
        "heat_score",
        "wind_score",
        "rain_score",
        "air_score",
        "river_score",
    }
    for estimate in estimates.values():
        assert estimate.available
        assert estimate.provenance
        assert estimate.method_reason
        assert estimate.unavailable_reason is None


def test_unsupported_rule_horizon_is_rejected():
    with pytest.raises(ValueError, match="Unsupported forecast horizon"):
        forecast_rule_estimates(_complete_row(), 4)


@pytest.mark.parametrize(
    ("field", "stale_value"),
    [
        ("method", "learned_model"),
        ("method", "development_fallback_rule"),
        ("validation_status", "era5_realized_validated"),
        ("uncertainty_method", "tree_spread_not_calibrated"),
        ("ci_lower", 10.0),
        ("ci_upper", 30.0),
        ("confidence_margin", 5.0),
    ],
)
def test_component_schema_rejects_stale_model_serving_contract(
    field,
    stale_value,
):
    payload = {
        "estimated_score": 25.0,
        "ci_lower": None,
        "ci_upper": None,
        "confidence_margin": None,
        "available": True,
        "method": "forecast_rule",
        "validation_status": "era5_backtested_limited",
        "uncertainty_method": "none",
        "provenance": "same-vintage weather forecast",
        "method_reason": "explicit operational baseline",
        "unavailable_reason": None,
    }
    payload[field] = stale_value

    with pytest.raises(ValidationError):
        ComponentForecast(**payload)


@pytest.mark.parametrize(
    ("field", "stale_value"),
    [
        ("model_version", "42"),
        ("total_ci_lower", 10.0),
        ("total_ci_upper", 30.0),
        ("total_confidence_margin", 5.0),
        ("model_target_components", ["heat"]),
        ("rule_based_components", ["heat", "rain", "wind", "air", "river"]),
    ],
)
def test_response_schema_rejects_stale_model_policy_fields(field, stale_value):
    component = {
        "estimated_score": 25.0,
        "ci_lower": None,
        "ci_upper": None,
        "confidence_margin": None,
        "available": True,
        "method": "forecast_rule",
        "validation_status": "era5_backtested_limited",
        "uncertainty_method": "none",
        "provenance": "same-vintage weather forecast",
        "method_reason": "explicit operational baseline",
        "unavailable_reason": None,
    }
    payload = {
        "city_id": "paris_fr",
        "horizon_days": 1,
        "prediction_date": "2026-07-19",
        "current_tipping_score": 20.0,
        "estimated_total_tipping_score": 25.0,
        "total_confidence_margin": None,
        "total_ci_lower": None,
        "total_ci_upper": None,
        "total_uncertainty_method": "none",
        "forecast_primary_driver": "Heat",
        "forecast_primary_driver_method": "forecast_rule",
        "sub_scores_forecast": {"heat_score": component},
        "weather_trajectory": {"temp_max_plus_1d": 30.0},
        "prediction_source": "same_vintage_forecast_rules",
        "model_version": None,
        "forecast_method": "forecast_rules_baseline",
        "model_target_components": [],
        "rule_based_components": ["heat", "wind", "rain", "air", "river"],
        "feature_schema_version": "3",
        "feature_ingestion_run_id": "run-1",
        "feature_ingested_at_utc": "2026-07-19T05:00:00Z",
        "forecast_origin_time_zone": "Europe/Paris",
    }
    payload[field] = stale_value

    with pytest.raises(ValidationError):
        CityForecastResponse(**payload)
