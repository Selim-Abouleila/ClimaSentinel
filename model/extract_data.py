"""Export the point-in-time-safe Heat/Rain training contract from BigQuery."""

from __future__ import annotations

import os
from pathlib import Path
import re
from typing import Any

import numpy as np
import pandas as pd

from backend.app.ml_pipeline import (
    ALL_CITIES,
    FEATURE_COLUMNS,
    FORECAST_HORIZONS,
    NUMERIC_FEATURE_COLUMNS,
    TARGET_COLUMNS,
)


DEFAULT_PROJECT_ID = "clima-sentinel"
DEFAULT_DATASET = "mart"
OUTPUT_PATH = Path("model/data/training_snapshot.csv")

LABEL_SOURCE = "open_meteo_era5"
SUPPORTED_TARGET_COMPONENTS = "heat,rain"
UNSUPPORTED_TARGET_COMPONENTS = "wind,air,river"
CANONICAL_VINTAGE_RULE = (
    "latest_complete_weather_vintage_per_city_local_origin_date"
)

OPTIONAL_NUMERIC_FEATURE_COLUMNS = (
    "european_aqi_max",
    "river_discharge_m3s",
    "aqi_forecast_plus_1d",
    "aqi_forecast_plus_2d",
    "aqi_forecast_plus_3d",
    "river_forecast_plus_1d",
    "river_forecast_plus_2d",
    "river_forecast_plus_3d",
    "river_forecast_plus_4d",
)
REQUIRED_NUMERIC_FEATURE_COLUMNS = tuple(
    column
    for column in NUMERIC_FEATURE_COLUMNS
    if column not in OPTIONAL_NUMERIC_FEATURE_COLUMNS
)

BASE_PROVENANCE_COLUMNS = (
    "forecast_origin_date",
    "ingestion_run_id",
    "ingested_at_utc",
    "forecast_origin_time_zone",
)

HORIZON_PROVENANCE_COLUMNS = tuple(
    column
    for horizon in FORECAST_HORIZONS
    for column in (
        f"target_date_{horizon}d",
        f"realized_weather_ingestion_run_id_{horizon}d",
        f"realized_weather_ingested_at_utc_{horizon}d",
        f"next_day_weather_ingestion_run_id_{horizon}d",
        f"next_day_weather_ingested_at_utc_{horizon}d",
        f"heat_label_available_at_utc_{horizon}d",
        f"rain_label_available_at_utc_{horizon}d",
        f"labels_available_at_utc_{horizon}d",
    )
)

CONTRACT_COLUMNS = (
    "training_labels_available_at_utc",
    "label_source",
    "supported_target_components",
    "unsupported_target_components",
    "canonical_vintage_rule",
)


def _ordered_unique(columns: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(columns))


TRAINING_SNAPSHOT_COLUMNS = _ordered_unique(
    BASE_PROVENANCE_COLUMNS
    + FEATURE_COLUMNS
    + HORIZON_PROVENANCE_COLUMNS
    + TARGET_COLUMNS
    + CONTRACT_COLUMNS
)


def _validate_identifier(value: str, label: str) -> str:
    """Reject malformed environment-provided BigQuery identifiers."""
    if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError(f"Invalid BigQuery {label}: {value!r}")
    return value


def build_training_query(project_id: str, dataset: str) -> str:
    """Build an explicit projection of the versioned dbt training mart."""
    project_id = _validate_identifier(project_id, "project ID")
    dataset = _validate_identifier(dataset, "dataset")
    projection = ",\n            ".join(
        f"`{column}`" for column in TRAINING_SNAPSHOT_COLUMNS
    )
    return f"""
        SELECT
            {projection}
        FROM `{project_id}.{dataset}.mart_ml_training_examples`
        ORDER BY forecast_origin_date, city_id, ingestion_run_id
    """


def _require_exact_value(frame: pd.DataFrame, column: str, expected: str) -> None:
    actual = set(frame[column].dropna().astype(str).unique())
    if frame[column].isna().any() or actual != {expected}:
        raise ValueError(
            f"Training contract column {column!r} must equal {expected!r}; "
            f"found {sorted(actual)!r}"
        )


def validate_training_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Validate mart provenance without fabricating features or target labels."""
    if frame.empty:
        raise ValueError("mart_ml_training_examples returned no training examples")

    missing = [
        column for column in TRAINING_SNAPSHOT_COLUMNS if column not in frame.columns
    ]
    if missing:
        raise ValueError(
            "Training mart is missing required contract columns: "
            + ", ".join(missing)
        )

    validated = frame.loc[:, list(TRAINING_SNAPSHOT_COLUMNS)].copy()
    if validated[["city_id", "forecast_origin_date"]].isna().any().any():
        raise ValueError("Training grain columns cannot be null")
    for column in (
        "city_id",
        "ingestion_run_id",
        "forecast_origin_time_zone",
    ):
        if validated[column].isna().any() or validated[column].astype(
            str
        ).str.strip().eq("").any():
            raise ValueError(f"Training provenance column {column!r} cannot be blank")
    if validated.duplicated(["city_id", "forecast_origin_date"]).any():
        raise ValueError(
            "Training mart must contain one canonical row per "
            "(city_id, forecast_origin_date)"
        )
    unsupported_cities = sorted(set(validated["city_id"].astype(str)) - set(ALL_CITIES))
    if unsupported_cities:
        raise ValueError(
            "Training mart contains cities outside the model contract: "
            + ", ".join(unsupported_cities)
        )

    required_features = validated.loc[
        :, list(REQUIRED_NUMERIC_FEATURE_COLUMNS)
    ].apply(pd.to_numeric, errors="coerce")
    if not np.isfinite(required_features.to_numpy(dtype=float)).all():
        raise ValueError(
            "Required weather/model features must be complete and finite"
        )
    validated.loc[:, list(REQUIRED_NUMERIC_FEATURE_COLUMNS)] = required_features

    optional_source = validated.loc[:, list(OPTIONAL_NUMERIC_FEATURE_COLUMNS)]
    optional_features = optional_source.apply(pd.to_numeric, errors="coerce")
    invalid_optional = optional_features.isna() & ~optional_source.isna()
    optional_values = optional_features.to_numpy(dtype=float)
    if invalid_optional.any().any() or np.isinf(optional_values).any():
        raise ValueError(
            "Optional AQ/river features may be null but must otherwise be finite"
        )
    validated.loc[:, list(OPTIONAL_NUMERIC_FEATURE_COLUMNS)] = optional_features

    origin_dates = pd.to_datetime(
        validated["forecast_origin_date"], errors="coerce"
    ).dt.normalize()
    if origin_dates.isna().any():
        raise ValueError("forecast_origin_date contains invalid dates")

    ingestion_times = pd.to_datetime(
        validated["ingested_at_utc"], errors="coerce", utc=True
    )
    if ingestion_times.isna().any():
        raise ValueError("ingested_at_utc contains invalid timestamps")

    label_availability_columns: list[str] = []
    for horizon in FORECAST_HORIZONS:
        target_date_column = f"target_date_{horizon}d"
        target_dates = pd.to_datetime(
            validated[target_date_column], errors="coerce"
        ).dt.normalize()
        if target_dates.isna().any() or not target_dates.equals(
            origin_dates + pd.Timedelta(horizon, unit="D")
        ):
            raise ValueError(
                f"{target_date_column} must be exactly Day +{horizon} from "
                "forecast_origin_date"
            )

        source_columns = (
            f"realized_weather_ingestion_run_id_{horizon}d",
            f"realized_weather_ingested_at_utc_{horizon}d",
            f"next_day_weather_ingestion_run_id_{horizon}d",
            f"next_day_weather_ingested_at_utc_{horizon}d",
        )
        if validated.loc[:, list(source_columns)].isna().any().any():
            raise ValueError(
                f"Day +{horizon} realized-label source provenance cannot be null"
            )
        for run_id_column in source_columns[::2]:
            if validated[run_id_column].astype(str).str.strip().eq("").any():
                raise ValueError(
                    f"Day +{horizon} source run ID {run_id_column!r} cannot be blank"
                )

        realized_times = pd.to_datetime(
            validated[source_columns[1]], errors="coerce", utc=True
        )
        next_day_times = pd.to_datetime(
            validated[source_columns[3]], errors="coerce", utc=True
        )
        if realized_times.isna().any() or next_day_times.isna().any():
            raise ValueError(
                f"Day +{horizon} label source timestamps must be valid"
            )

        heat_available_column = f"heat_label_available_at_utc_{horizon}d"
        rain_available_column = f"rain_label_available_at_utc_{horizon}d"
        combined_available_column = f"labels_available_at_utc_{horizon}d"
        component_times = pd.DataFrame(
            {
                "heat": pd.to_datetime(
                    validated[heat_available_column], errors="coerce", utc=True
                ),
                "rain": pd.to_datetime(
                    validated[rain_available_column], errors="coerce", utc=True
                ),
            }
        )
        combined_times = pd.to_datetime(
            validated[combined_available_column], errors="coerce", utc=True
        )
        if component_times.isna().any().any() or combined_times.isna().any():
            raise ValueError(
                f"Day +{horizon} label availability timestamps cannot be null"
            )
        if (component_times.le(ingestion_times, axis=0)).any().any():
            raise ValueError(
                f"Day +{horizon} labels must become available strictly after "
                "forecast ingestion"
            )
        expected_heat_available = pd.concat(
            [realized_times, next_day_times], axis=1
        ).max(axis=1)
        if not component_times["heat"].equals(expected_heat_available):
            raise ValueError(
                f"Day +{horizon} Heat label availability must reflect both "
                "realized source vintages"
            )
        if not component_times["rain"].equals(realized_times):
            raise ValueError(
                f"Day +{horizon} Rain label availability must match its "
                "realized source vintage"
            )
        expected_combined = component_times.max(axis=1)
        if not combined_times.equals(expected_combined):
            raise ValueError(
                f"{combined_available_column} must equal the latest component "
                "availability timestamp"
            )
        label_availability_columns.append(combined_available_column)

    training_available = pd.to_datetime(
        validated["training_labels_available_at_utc"], errors="coerce", utc=True
    )
    expected_training_available = pd.concat(
        [
            pd.to_datetime(validated[column], errors="coerce", utc=True)
            for column in label_availability_columns
        ],
        axis=1,
    ).max(axis=1)
    if training_available.isna().any() or not training_available.equals(
        expected_training_available
    ):
        raise ValueError(
            "training_labels_available_at_utc must equal the latest horizon label "
            "availability timestamp"
        )

    numeric_targets = validated.loc[:, list(TARGET_COLUMNS)].apply(
        pd.to_numeric, errors="coerce"
    )
    target_values = numeric_targets.to_numpy(dtype=float)
    if not np.isfinite(target_values).all():
        raise ValueError("Realized Heat/Rain targets must be complete and finite")
    if ((target_values < 0.0) | (target_values > 100.0)).any():
        raise ValueError("Realized Heat/Rain targets must be within [0, 100]")
    validated.loc[:, list(TARGET_COLUMNS)] = numeric_targets

    _require_exact_value(validated, "label_source", LABEL_SOURCE)
    _require_exact_value(
        validated, "supported_target_components", SUPPORTED_TARGET_COMPONENTS
    )
    _require_exact_value(
        validated, "unsupported_target_components", UNSUPPORTED_TARGET_COMPONENTS
    )
    _require_exact_value(
        validated, "canonical_vintage_rule", CANONICAL_VINTAGE_RULE
    )

    # Do not fill or otherwise synthesize optional feature values here. Missing
    # AQ/flood inputs remain null in the snapshot and are handled by the fitted
    # preprocessing pipeline, preserving train/serve parity. Gust is required
    # because it belongs to the complete weather feature contract.
    return validated.sort_values(
        ["forecast_origin_date", "city_id", "ingestion_run_id"],
        kind="stable",
    ).reset_index(drop=True)


def extract_data(
    client: Any | None = None,
    output_path: str | Path = OUTPUT_PATH,
) -> pd.DataFrame:
    """Query, validate, and persist the dbt-owned supervised dataset."""
    project_id = os.getenv("GCP_PROJECT_ID", DEFAULT_PROJECT_ID)
    dataset = os.getenv("BQ_DATASET", DEFAULT_DATASET)
    query = build_training_query(project_id, dataset)
    if client is None:
        from google.cloud import bigquery

        query_client = bigquery.Client(project=project_id)
    else:
        query_client = client

    print("Extracting point-in-time-safe examples from mart_ml_training_examples...")
    frame = query_client.query(query).to_dataframe()
    validated = validate_training_frame(frame)

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    validated.to_csv(destination, index=False)
    print(f"Successfully exported {len(validated)} rows to {destination}")
    return validated


if __name__ == "__main__":
    extract_data()
