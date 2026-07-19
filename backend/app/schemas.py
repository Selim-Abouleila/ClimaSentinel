"""Typed API contracts for the hybrid forecast endpoint."""

from typing import Literal

from pydantic import BaseModel


ComponentMethod = Literal[
    "learned_model",
    "forecast_rule",
    "development_fallback_rule",
]
ValidationStatus = Literal[
    "era5_realized_validated",
    "not_observation_validated",
]
UncertaintyMethod = Literal["tree_spread_not_calibrated", "none"]


class ComponentForecast(BaseModel):
    estimated_score: float | None
    ci_lower: float | None
    ci_upper: float | None
    confidence_margin: float | None
    available: bool
    method: ComponentMethod
    validation_status: ValidationStatus
    uncertainty_method: UncertaintyMethod
    unavailable_reason: str | None = None


class CityForecastResponse(BaseModel):
    city_id: str
    horizon_days: int
    prediction_date: str
    current_tipping_score: float
    estimated_total_tipping_score: float
    total_confidence_margin: float | None
    total_ci_lower: float | None
    total_ci_upper: float | None
    total_uncertainty_method: UncertaintyMethod
    forecast_primary_driver: str
    forecast_primary_driver_method: ComponentMethod
    sub_scores_forecast: dict[str, ComponentForecast]
    weather_trajectory: dict[str, float | None]

    # `prediction_source` is retained for compatibility and describes the
    # Heat/Rain estimator only, not every component in this hybrid response.
    prediction_source: str
    model_version: str | None
    forecast_method: Literal["hybrid_ml_and_forecast_rules"]
    model_target_components: list[str]
    rule_based_components: list[str]
    feature_schema_version: str
    feature_ingestion_run_id: str
    feature_ingested_at_utc: str
    forecast_origin_time_zone: str

