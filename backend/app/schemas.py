"""Typed API contracts exposed by the ClimaSentinel backend."""

from datetime import date as CalendarDate
from math import isclose
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, BaseModel, Field, model_validator


ComponentMethod = Literal["forecast_rule"]
ValidationStatus = Literal[
    "era5_backtested_limited",
    "era5_backtested_insufficient_skill",
    "not_observation_validated",
]
UncertaintyMethod = Literal["none"]
SignalStatus = Literal["available", "not_monitored", "unavailable"]
SignalScore = Annotated[float | None, Field(ge=0.0, le=100.0)]
CoverageRatio = Annotated[float | None, Field(ge=0.0, le=1.0)]
TippingScore = Annotated[float | None, Field(ge=0.0, le=100.0)]


class CurrentCityScoreResponse(BaseModel):
    """One city in the operational overview ranking."""

    operational_ingestion_run_id: str
    operational_ingested_at_utc: AwareDatetime
    city_id: str
    current_tipping_score: TippingScore
    current_primary_driver: str | None
    current_score_available: bool
    monitored_factor_count: Annotated[int, Field(ge=0, le=5)]
    available_factor_count: Annotated[int, Field(ge=0, le=5)]
    overall_coverage: CoverageRatio
    rank: Annotated[int, Field(ge=1)]

    @model_validator(mode="after")
    def aggregate_availability_is_consistent(self) -> Self:
        if self.current_score_available != (self.current_tipping_score is not None):
            raise ValueError(
                "current_score_available must reflect whether "
                "current_tipping_score is non-null"
            )
        if self.available_factor_count > self.monitored_factor_count:
            raise ValueError(
                "available_factor_count cannot exceed monitored_factor_count"
            )
        if self.current_score_available != (self.available_factor_count > 0):
            raise ValueError(
                "current_score_available must reflect whether at least one "
                "factor is available"
            )
        if self.monitored_factor_count and self.overall_coverage is None:
            raise ValueError(
                "overall_coverage must be non-null when factors are monitored"
            )
        if not self.monitored_factor_count and self.overall_coverage is not None:
            raise ValueError(
                "overall_coverage must be null when no factors are monitored"
            )
        if not self.current_score_available and self.current_primary_driver not in {
            None,
            "Unavailable",
        }:
            raise ValueError(
                "current_primary_driver must be null or 'Unavailable' when the "
                "overall score is unavailable"
            )
        return self


class SignalScores(BaseModel):
    """Nullable factor scores and explicit signal-availability metadata.

    Score fields deliberately remain nullable. A missing or unmonitored input
    must never cross the API boundary as a synthetic zero-risk score.
    """

    heat_score: SignalScore
    heat_status: SignalStatus
    heat_monitored: bool
    heat_available: bool
    heat_coverage: CoverageRatio

    wind_score: SignalScore
    wind_status: SignalStatus
    wind_monitored: bool
    wind_available: bool
    wind_coverage: CoverageRatio

    rain_score: SignalScore
    rain_status: SignalStatus
    rain_monitored: bool
    rain_available: bool
    rain_coverage: CoverageRatio

    air_score: SignalScore
    air_status: SignalStatus
    air_monitored: bool
    air_available: bool
    air_coverage: CoverageRatio

    river_score: SignalScore
    river_status: SignalStatus
    river_monitored: bool
    river_available: bool
    river_coverage: CoverageRatio

    @model_validator(mode="after")
    def availability_metadata_is_consistent(self) -> Self:
        """Reject contradictory score/status combinations at the API edge."""
        for factor in ("heat", "wind", "rain", "air", "river"):
            score = getattr(self, f"{factor}_score")
            status = getattr(self, f"{factor}_status")
            monitored = getattr(self, f"{factor}_monitored")
            available = getattr(self, f"{factor}_available")
            coverage = getattr(self, f"{factor}_coverage")

            if status == "available":
                if (
                    not monitored
                    or not available
                    or score is None
                    or coverage is None
                ):
                    raise ValueError(
                        f"{factor} status 'available' requires monitored=true, "
                        "available=true, a non-null score and non-null coverage"
                    )
                if coverage != 1.0:
                    raise ValueError(
                        f"{factor} status 'available' requires coverage=1.0"
                    )
            elif status == "not_monitored":
                if monitored or available or score is not None or coverage is not None:
                    raise ValueError(
                        f"{factor} status 'not_monitored' requires monitored=false, "
                        "available=false, score=null and coverage=null"
                    )
            elif (
                not monitored
                or available
                or score is not None
                or coverage is None
            ):
                raise ValueError(
                    f"{factor} status 'unavailable' requires monitored=true, "
                    "available=false, score=null and non-null coverage"
                )
            elif coverage >= 1.0:
                raise ValueError(
                    f"{factor} status 'unavailable' requires coverage below 1.0"
                )

        return self

    def monitored_count(self) -> int:
        return sum(
            bool(getattr(self, f"{factor}_monitored"))
            for factor in ("heat", "wind", "rain", "air", "river")
        )

    def available_count(self) -> int:
        return sum(
            bool(getattr(self, f"{factor}_available"))
            for factor in ("heat", "wind", "rain", "air", "river")
        )

    def maximum_available_score(self) -> float | None:
        scores = [
            getattr(self, f"{factor}_score")
            for factor in ("heat", "wind", "rain", "air", "river")
            if getattr(self, f"{factor}_available")
        ]
        return max(scores) if scores else None

    def mean_monitored_coverage(self) -> float | None:
        coverage = [
            getattr(self, f"{factor}_coverage")
            for factor in ("heat", "wind", "rain", "air", "river")
            if getattr(self, f"{factor}_monitored")
        ]
        return sum(coverage) / len(coverage) if coverage else None

    def validate_aggregate(
        self,
        *,
        score: float | None,
        driver: str | None,
        score_available: bool,
        monitored_factor_count: int,
        available_factor_count: int,
        overall_coverage: float | None,
    ) -> None:
        """Validate that an aggregate is derived only from available factors."""
        expected_score = self.maximum_available_score()
        expected_monitored = self.monitored_count()
        expected_available = self.available_count()
        expected_coverage = self.mean_monitored_coverage()

        if monitored_factor_count != expected_monitored:
            raise ValueError("monitored_factor_count must equal factor monitoring flags")
        if available_factor_count != expected_available:
            raise ValueError("available_factor_count must equal factor availability flags")
        if score_available != (expected_score is not None):
            raise ValueError("aggregate availability must reflect available factor scores")
        if (score is None) != (expected_score is None):
            raise ValueError("aggregate score nullability must reflect available factors")
        if score is not None and expected_score is not None and not isclose(
            score,
            expected_score,
            rel_tol=0.0,
            abs_tol=0.05,
        ):
            raise ValueError("aggregate score must equal the maximum available factor score")
        if expected_coverage is None:
            if overall_coverage is not None:
                raise ValueError("overall_coverage must be null without monitored factors")
        elif overall_coverage is None or not isclose(
            overall_coverage,
            expected_coverage,
            rel_tol=0.0,
            abs_tol=0.001,
        ):
            raise ValueError("overall_coverage must equal mean monitored-factor coverage")
        if expected_score is None and driver not in {None, "Unavailable"}:
            raise ValueError(
                "aggregate driver must be null or 'Unavailable' without an available score"
            )


class CityScoreDetailResponse(SignalScores):
    """Current operational score detail for one city."""

    operational_ingestion_run_id: str
    operational_ingested_at_utc: AwareDatetime
    city_id: str
    score_date: CalendarDate
    current_tipping_score: TippingScore
    current_primary_driver: str | None
    current_score_available: bool
    monitored_factor_count: Annotated[int, Field(ge=0, le=5)]
    available_factor_count: Annotated[int, Field(ge=0, le=5)]
    overall_coverage: CoverageRatio

    @model_validator(mode="after")
    def aggregate_availability_is_consistent(self) -> Self:
        self.validate_aggregate(
            score=self.current_tipping_score,
            driver=self.current_primary_driver,
            score_available=self.current_score_available,
            monitored_factor_count=self.monitored_factor_count,
            available_factor_count=self.available_factor_count,
            overall_coverage=self.overall_coverage,
        )
        return self


class CityScoreHistoryResponse(SignalScores):
    """One daily historical city-score row."""

    operational_ingestion_run_id: str
    operational_ingested_at_utc: AwareDatetime
    city_id: str
    date: CalendarDate
    temperature_2m_max: float | None
    precipitation_sum_mm: float | None
    wind_gusts_10m_max: float | None
    european_aqi_max: float | None
    river_discharge_m3s: float | None
    monitored_factor_count: Annotated[int, Field(ge=0, le=5)]
    available_factor_count: Annotated[int, Field(ge=0, le=5)]
    overall_coverage: CoverageRatio
    global_score_available: bool
    global_tipping_score: TippingScore
    primary_driver: str | None

    @model_validator(mode="after")
    def aggregate_availability_is_consistent(self) -> Self:
        self.validate_aggregate(
            score=self.global_tipping_score,
            driver=self.primary_driver,
            score_available=self.global_score_available,
            monitored_factor_count=self.monitored_factor_count,
            available_factor_count=self.available_factor_count,
            overall_coverage=self.overall_coverage,
        )
        return self


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
