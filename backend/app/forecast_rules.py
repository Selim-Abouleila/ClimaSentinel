"""Deterministic same-vintage operational forecast rules.

The deployed policy intentionally serves these rules while the learned Heat and
Rain challengers fail promotion. Heat is the one rule that has demonstrated
useful backtest performance against Open-Meteo archive/reanalysis data. Rain is
marked as backtested with insufficient skill; Wind, Air Quality and River
remain without honest observed labels.
"""

from dataclasses import dataclass
import math
from typing import Any, Mapping


SUPPORTED_HORIZONS = (1, 2, 3)


@dataclass(frozen=True)
class RuleEstimate:
    """A deterministic component score or an explicit source-data gap."""

    score: float | None
    validation_status: str
    provenance: str
    method_reason: str
    unavailable_reason: str | None = None

    @property
    def available(self) -> bool:
        return self.score is not None


def _finite_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric_value):
        return None
    return numeric_value


def _flag(row: Mapping[str, Any], column: str, default: bool = False) -> bool:
    value = row.get(column, default)
    return value is True or value == 1


def _clip_score(value: float) -> float:
    return round(min(100.0, max(0.0, value)), 1)


def forecast_rule_estimates(
    row: Mapping[str, Any],
    horizon_days: int,
) -> dict[str, RuleEstimate]:
    """Score all five components from one exact forecast vintage.

    Heat consumes the requested day's maximum temperature, the next day's
    maximum temperature, and the requested target month's climatological
    normal. Rain consumes the requested day's precipitation. Missing optional
    AQ/flood inputs remain unavailable. No value is borrowed from another
    horizon, run, or city, and absence is never reported as zero risk. Day +3
    Heat and River deliberately consume Day +4 values from the same vintage.
    """

    if horizon_days not in SUPPORTED_HORIZONS:
        raise ValueError(
            f"Unsupported forecast horizon {horizon_days}; expected one of "
            f"{SUPPORTED_HORIZONS}"
        )

    next_horizon = horizon_days + 1
    weather_is_complete = _flag(
        row,
        f"weather_has_24_hour_coverage_plus_{horizon_days}d",
    ) and _flag(
        row,
        f"has_complete_weather_values_plus_{horizon_days}d",
    )
    next_weather_is_complete = _flag(
        row,
        f"weather_has_24_hour_coverage_plus_{next_horizon}d",
    ) and _flag(
        row,
        f"has_complete_weather_values_plus_{next_horizon}d",
    )

    temperature = _finite_float(
        row.get(f"temp_forecast_plus_{horizon_days}d")
    )
    next_temperature = _finite_float(
        row.get(f"temp_forecast_plus_{next_horizon}d")
    )
    target_month_normal = _finite_float(
        row.get("target_normal_temperature_2m_max")
    )
    heat_provenance = (
        "same-vintage weather forecast plus target-month city climatology"
    )
    heat_reason = (
        "Reviewed operational baseline; offline challenger promotion does not "
        "change serving without a separate integration decision"
    )
    if (
        temperature is None
        or next_temperature is None
        or target_month_normal is None
        or not weather_is_complete
        or not next_weather_is_complete
    ):
        heat = RuleEstimate(
            score=None,
            validation_status="era5_backtested_limited",
            provenance=heat_provenance,
            method_reason=heat_reason,
            unavailable_reason=(
                "Complete same-vintage target-day/next-day temperatures and "
                "target-month climatology are required"
            ),
        )
    else:
        heat = RuleEstimate(
            score=_clip_score(
                (temperature - target_month_normal) * 5.0
                + max(0.0, next_temperature - temperature) * 5.0
            ),
            validation_status="era5_backtested_limited",
            provenance=heat_provenance,
            method_reason=heat_reason,
        )

    precipitation = _finite_float(
        row.get(f"precip_forecast_plus_{horizon_days}d")
    )
    rain_provenance = "same-vintage daily precipitation forecast"
    rain_reason = (
        "Reviewed operational baseline; its ERA5 backtest showed insufficient "
        "predictive skill, and challenger promotion does not change serving "
        "without a separate integration decision"
    )
    if precipitation is None or not weather_is_complete:
        rain = RuleEstimate(
            score=None,
            validation_status="era5_backtested_insufficient_skill",
            provenance=rain_provenance,
            method_reason=rain_reason,
            unavailable_reason=(
                "Complete same-vintage precipitation forecast is unavailable"
            ),
        )
    else:
        rain = RuleEstimate(
            score=_clip_score(precipitation * 2.0),
            validation_status="era5_backtested_insufficient_skill",
            provenance=rain_provenance,
            method_reason=rain_reason,
        )

    gust = _finite_float(row.get(f"wind_gusts_forecast_plus_{horizon_days}d"))
    wind_is_complete = _flag(
        row,
        f"weather_has_24_hour_coverage_plus_{horizon_days}d",
    ) and _flag(
        row,
        f"has_complete_weather_values_plus_{horizon_days}d",
    )
    if gust is None or not wind_is_complete:
        wind = RuleEstimate(
            score=None,
            validation_status="not_observation_validated",
            provenance="same-vintage wind-gust forecast",
            method_reason=(
                "Deterministic forecast rule; observed historical gust labels "
                "are not currently ingested"
            ),
            unavailable_reason="Same-vintage wind-gust forecast is unavailable",
        )
    else:
        wind = RuleEstimate(
            score=_clip_score(max(0.0, gust - 40.0) * 2.5),
            validation_status="not_observation_validated",
            provenance="same-vintage wind-gust forecast",
            method_reason=(
                "Deterministic forecast rule; observed historical gust labels "
                "are not currently ingested"
            ),
        )

    aqi = _finite_float(row.get(f"aqi_forecast_plus_{horizon_days}d"))
    aqi_is_complete = (
        _flag(row, f"has_air_quality_forecast_plus_{horizon_days}d")
        and _flag(row, f"air_quality_has_24_hour_coverage_plus_{horizon_days}d")
        and _flag(row, f"has_complete_air_quality_values_plus_{horizon_days}d")
    )
    if aqi is None or not aqi_is_complete:
        air = RuleEstimate(
            score=None,
            validation_status="not_observation_validated",
            provenance="same-vintage air-quality forecast",
            method_reason=(
                "Deterministic forecast rule; observed historical air-quality "
                "labels are not currently ingested"
            ),
            unavailable_reason="Same-vintage air-quality forecast is unavailable",
        )
    else:
        air = RuleEstimate(
            score=_clip_score((aqi - 40.0) * 1.67),
            validation_status="not_observation_validated",
            provenance="same-vintage air-quality forecast",
            method_reason=(
                "Deterministic forecast rule; observed historical air-quality "
                "labels are not currently ingested"
            ),
        )

    discharge = _finite_float(
        row.get(f"river_forecast_plus_{horizon_days}d")
    )
    next_discharge = _finite_float(
        row.get(f"river_forecast_plus_{next_horizon}d")
    )
    flood_is_present = _flag(
        row,
        f"has_flood_forecast_plus_{horizon_days}d",
    )
    next_flood_is_present = _flag(
        row,
        f"has_flood_forecast_plus_{next_horizon}d",
    )

    if discharge is None or not flood_is_present:
        river = RuleEstimate(
            score=None,
            validation_status="not_observation_validated",
            provenance="same-vintage river-discharge forecast",
            method_reason=(
                "Deterministic forecast rule; observed historical river "
                "discharge labels are not currently ingested"
            ),
            unavailable_reason="Same-vintage river forecast is unavailable",
        )
    elif discharge <= 50.0:
        # This is the documented operational rule: below the activation
        # threshold, next-day velocity does not contribute.
        river = RuleEstimate(
            score=0.0,
            validation_status="not_observation_validated",
            provenance="same-vintage river-discharge forecast",
            method_reason=(
                "Deterministic forecast rule; observed historical river "
                "discharge labels are not currently ingested"
            ),
        )
    elif next_discharge is None or not next_flood_is_present:
        river = RuleEstimate(
            score=None,
            validation_status="not_observation_validated",
            provenance="same-vintage river-discharge forecast",
            method_reason=(
                "Deterministic forecast rule; observed historical river "
                "discharge labels are not currently ingested"
            ),
            unavailable_reason=(
                "Next-day same-vintage river forecast is unavailable for velocity"
            ),
        )
    else:
        positive_velocity = max(
            0.0,
            (next_discharge - discharge) / discharge,
        )
        river = RuleEstimate(
            score=_clip_score(positive_velocity * 200.0),
            validation_status="not_observation_validated",
            provenance="same-vintage river-discharge forecast",
            method_reason=(
                "Deterministic forecast rule; observed historical river "
                "discharge labels are not currently ingested"
            ),
        )

    return {
        "heat_score": heat,
        "wind_score": wind,
        "rain_score": rain,
        "air_score": air,
        "river_score": river,
    }
