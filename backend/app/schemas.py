"""Typed API contracts for the explicit forecast-rule baseline endpoint."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field


ComponentMethod = Literal["forecast_rule"]
ValidationStatus = Literal[
    "era5_backtested_limited",
    "era5_backtested_insufficient_skill",
    "not_observation_validated",
]
UncertaintyMethod = Literal["none"]


class ComponentForecast(BaseModel):
    estimated_score: float | None
    ci_lower: None = None
    ci_upper: None = None
    confidence_margin: None = None
    available: bool
    method: ComponentMethod
    validation_status: ValidationStatus
    uncertainty_method: UncertaintyMethod
    provenance: str
    method_reason: str
    unavailable_reason: str | None = None


class CityForecastResponse(BaseModel):
    city_id: str
    horizon_days: int
    prediction_date: str
    current_tipping_score: float
    estimated_total_tipping_score: float
    total_confidence_margin: None = None
    total_ci_lower: None = None
    total_ci_upper: None = None
    total_uncertainty_method: UncertaintyMethod
    forecast_primary_driver: str
    forecast_primary_driver_method: ComponentMethod
    sub_scores_forecast: dict[str, ComponentForecast]
    weather_trajectory: dict[str, float | None]

    # These compatibility fields make the active serving policy explicit.
    # No registered-model version is claimed while every component uses a rule.
    prediction_source: Literal["same_vintage_forecast_rules"]
    model_version: None = None
    forecast_method: Literal["forecast_rules_baseline"]
    model_target_components: Annotated[list[str], Field(max_length=0)]
    rule_based_components: tuple[
        Literal["heat"],
        Literal["wind"],
        Literal["rain"],
        Literal["air"],
        Literal["river"],
    ]
    feature_schema_version: str
    feature_ingestion_run_id: str
    feature_ingested_at_utc: str
    forecast_origin_time_zone: str
