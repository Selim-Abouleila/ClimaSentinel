"""Tests for the point-in-time-safe BigQuery training extraction contract."""

from pathlib import Path
import sys
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from app.ml_pipeline import FEATURE_COLUMNS, FORECAST_HORIZONS, TARGET_COLUMNS


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT))
try:
    from model import extract_data
finally:
    sys.path.remove(str(REPOSITORY_ROOT))


def valid_training_frame(
    origins: pd.DatetimeIndex | None = None,
    cities: tuple[str, ...] = ("paris_fr",),
) -> pd.DataFrame:
    if origins is None:
        origins = pd.date_range("2026-05-01", periods=2, freq="D")
    rows = []
    for origin in origins:
        for city_index, city_id in enumerate(cities):
            row = {
                column: float(index + city_index + 1)
                for index, column in enumerate(FEATURE_COLUMNS)
                if column != "city_id"
            }
            row.update(
                {
                    "forecast_origin_date": origin.date().isoformat(),
                    "ingestion_run_id": f"forecast-{origin.date()}-{city_id}",
                    "ingested_at_utc": f"{origin.date()}T06:00:00Z",
                    "forecast_origin_time_zone": "Europe/Paris",
                    "city_id": city_id,
                    "training_labels_available_at_utc": (
                        origin + pd.Timedelta(108, unit="h")
                    ).isoformat(),
                    "label_source": extract_data.LABEL_SOURCE,
                    "supported_target_components": (
                        extract_data.SUPPORTED_TARGET_COMPONENTS
                    ),
                    "unsupported_target_components": (
                        extract_data.UNSUPPORTED_TARGET_COMPONENTS
                    ),
                    "canonical_vintage_rule": (
                        extract_data.CANONICAL_VINTAGE_RULE
                    ),
                }
            )
            for horizon in FORECAST_HORIZONS:
                target_date = origin + pd.Timedelta(horizon, unit="D")
                realized_available = target_date + pd.Timedelta(1, unit="D")
                next_day_available = target_date + pd.Timedelta(36, unit="h")
                row.update(
                    {
                        f"target_date_{horizon}d": target_date.date().isoformat(),
                        f"realized_weather_ingestion_run_id_{horizon}d": (
                            f"realized-{target_date.date()}"
                        ),
                        f"realized_weather_ingested_at_utc_{horizon}d": (
                            realized_available.isoformat()
                        ),
                        f"next_day_weather_ingestion_run_id_{horizon}d": (
                            f"next-day-{target_date.date()}"
                        ),
                        f"next_day_weather_ingested_at_utc_{horizon}d": (
                            next_day_available.isoformat()
                        ),
                        f"heat_label_available_at_utc_{horizon}d": (
                            next_day_available.isoformat()
                        ),
                        f"rain_label_available_at_utc_{horizon}d": (
                            realized_available.isoformat()
                        ),
                        f"labels_available_at_utc_{horizon}d": (
                            next_day_available.isoformat()
                        ),
                        f"future_heat_score_{horizon}d": 20.0 + horizon,
                        f"future_rain_score_{horizon}d": 2.0 + horizon,
                    }
                )
            rows.append(row)
    return pd.DataFrame(rows)


def test_extracts_explicit_training_mart_contract_without_imputation(tmp_path):
    frame = valid_training_frame()
    frame.loc[0, "european_aqi_max"] = np.nan
    frame.loc[0, "river_discharge_m3s"] = np.nan
    query_job = MagicMock()
    query_job.to_dataframe.return_value = frame
    client = MagicMock()
    client.query.return_value = query_job
    destination = tmp_path / "training_snapshot.csv"

    validated = extract_data.extract_data(client=client, output_path=destination)

    query = client.query.call_args.args[0]
    assert ".mart_ml_training_examples`" in query
    assert "mart_ml_feature_store" not in query
    assert "mart_city_score_history" not in query
    assert "SELECT *" not in query.upper()
    for column in (*FEATURE_COLUMNS, *TARGET_COLUMNS):
        assert f"`{column}`" in query
    assert pd.isna(validated.loc[0, "european_aqi_max"])
    assert pd.isna(validated.loc[0, "river_discharge_m3s"])
    persisted = pd.read_csv(destination)
    assert pd.isna(persisted.loc[0, "european_aqi_max"])
    assert pd.isna(persisted.loc[0, "river_discharge_m3s"])


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        (
            lambda frame: frame.__setitem__(
                "future_heat_score_1d", np.nan
            ),
            "complete and finite",
        ),
        (
            lambda frame: frame.__setitem__(
                "target_date_2d", "2026-05-20"
            ),
            r"exactly Day \+2",
        ),
        (
            lambda frame: frame.__setitem__(
                "heat_label_available_at_utc_1d", frame["ingested_at_utc"]
            ),
            "strictly after",
        ),
        (
            lambda frame: frame.__setitem__(
                "label_source", "forecast_proxy"
            ),
            "open_meteo_era5",
        ),
        (
            lambda frame: frame.__setitem__("temperature_2m_max", np.nan),
            "complete and finite",
        ),
        (
            lambda frame: frame.__setitem__("city_id", "unknown_city"),
            "outside the model contract",
        ),
    ),
)
def test_rejects_broken_label_or_provenance_contract(mutation, message):
    frame = valid_training_frame()
    mutation(frame)

    with pytest.raises(ValueError, match=message):
        extract_data.validate_training_frame(frame)


def test_rejects_more_than_one_vintage_per_city_origin():
    frame = valid_training_frame().iloc[[0]].copy()
    duplicate = frame.copy()
    duplicate["ingestion_run_id"] = "retry-run"

    with pytest.raises(ValueError, match="one canonical row"):
        extract_data.validate_training_frame(
            pd.concat([frame, duplicate], ignore_index=True)
        )
