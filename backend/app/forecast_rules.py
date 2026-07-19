"""Deterministic same-vintage rules for components without realized labels."""

from dataclasses import dataclass
import math
from typing import Any, Mapping


SUPPORTED_HORIZONS = (1, 2, 3)


@dataclass(frozen=True)
class RuleEstimate:
    """A deterministic component score or an explicit source-data gap."""

    score: float | None
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
    """Score Wind, AQ and River from one exact forecast vintage.

    Missing optional AQ/flood inputs remain unavailable. No value is borrowed
    from another horizon, run, or city, and absence is never reported as zero
    risk. Day +3 River deliberately consumes Day +4 discharge for velocity.
    """

    if horizon_days not in SUPPORTED_HORIZONS:
        raise ValueError(
            f"Unsupported forecast horizon {horizon_days}; expected one of "
            f"{SUPPORTED_HORIZONS}"
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
            unavailable_reason="Same-vintage wind-gust forecast is unavailable",
        )
    else:
        wind = RuleEstimate(_clip_score(max(0.0, gust - 40.0) * 2.5))

    aqi = _finite_float(row.get(f"aqi_forecast_plus_{horizon_days}d"))
    aqi_is_complete = (
        _flag(row, f"has_air_quality_forecast_plus_{horizon_days}d")
        and _flag(row, f"air_quality_has_24_hour_coverage_plus_{horizon_days}d")
        and _flag(row, f"has_complete_air_quality_values_plus_{horizon_days}d")
    )
    if aqi is None or not aqi_is_complete:
        air = RuleEstimate(
            score=None,
            unavailable_reason="Same-vintage air-quality forecast is unavailable",
        )
    else:
        air = RuleEstimate(_clip_score((aqi - 40.0) * 1.67))

    next_horizon = horizon_days + 1
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
            unavailable_reason="Same-vintage river forecast is unavailable",
        )
    elif discharge <= 50.0:
        # This is the documented operational rule: below the activation
        # threshold, next-day velocity does not contribute.
        river = RuleEstimate(0.0)
    elif next_discharge is None or not next_flood_is_present:
        river = RuleEstimate(
            score=None,
            unavailable_reason=(
                "Next-day same-vintage river forecast is unavailable for velocity"
            ),
        )
    else:
        positive_velocity = max(
            0.0,
            (next_discharge - discharge) / discharge,
        )
        river = RuleEstimate(_clip_score(positive_velocity * 200.0))

    return {
        "wind_score": wind,
        "air_score": air,
        "river_score": river,
    }

