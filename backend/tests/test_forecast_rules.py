"""Deterministic rule tests for forecast-only hybrid components."""

import pytest

from app.forecast_rules import forecast_rule_estimates


def _complete_row() -> dict:
    row = {}
    for horizon in range(1, 5):
        row[f"weather_has_24_hour_coverage_plus_{horizon}d"] = True
        row[f"has_complete_weather_values_plus_{horizon}d"] = True
        row[f"has_air_quality_forecast_plus_{horizon}d"] = True
        row[f"air_quality_has_24_hour_coverage_plus_{horizon}d"] = True
        row[f"has_complete_air_quality_values_plus_{horizon}d"] = True
        row[f"has_flood_forecast_plus_{horizon}d"] = True
        row[f"wind_gusts_forecast_plus_{horizon}d"] = 52.0
        row[f"aqi_forecast_plus_{horizon}d"] = 70.0
        row[f"river_forecast_plus_{horizon}d"] = 60.0 + horizon * 6.0
    return row


@pytest.mark.parametrize("horizon", [1, 2, 3])
def test_rules_use_requested_same_vintage_horizon(horizon):
    row = _complete_row()

    estimates = forecast_rule_estimates(row, horizon)

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


def test_below_threshold_river_is_zero_without_next_day_value():
    row = _complete_row()
    row["river_forecast_plus_2d"] = 50.0
    row["river_forecast_plus_3d"] = None
    row["has_flood_forecast_plus_3d"] = False

    estimate = forecast_rule_estimates(row, 2)["river_score"]

    assert estimate.available
    assert estimate.score == 0.0


def test_missing_optional_sources_are_unavailable_not_zero():
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

    estimates = forecast_rule_estimates(row, 1)

    assert estimates["wind_score"].score == 100.0
    assert estimates["air_score"].score == 0.0
    assert estimates["river_score"].score == 100.0


def test_unsupported_rule_horizon_is_rejected():
    with pytest.raises(ValueError, match="Unsupported forecast horizon"):
        forecast_rule_estimates(_complete_row(), 4)
