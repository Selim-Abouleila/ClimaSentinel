"""Same-vintage Heat/Rain rule baselines used for challenger evaluation.

These functions deliberately consume only the forecast features that were
available in the candidate row's recorded ingestion vintage.  They must never
use realized values or fit thresholds from the held-out labels.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from backend.app.ml_pipeline import ALL_CITIES, FORECAST_HORIZONS


RULE_BASELINE_CONTRACT = "same_vintage_heat_rain_rules_v2_target_month_normal"
RULE_BASELINE_SCORE_NAMES = ("heat_score", "rain_score")
CITY_MONTHLY_NORMALS_PATH = (
    Path(__file__).resolve().parents[1]
    / "transform"
    / "seeds"
    / "city_monthly_normals.csv"
)
NORMAL_COLUMNS = ("city_id", "month", "normal_temperature_2m_max")


def load_city_monthly_heat_normals(
    path: Path = CITY_MONTHLY_NORMALS_PATH,
) -> pd.DataFrame:
    """Load and strictly validate the static city/month Heat normal lookup."""

    normals = pd.read_csv(path)
    missing_columns = [column for column in NORMAL_COLUMNS if column not in normals]
    if missing_columns:
        raise ValueError(
            "City monthly normals are missing required columns: "
            + ", ".join(missing_columns)
        )

    validated = normals.loc[:, list(NORMAL_COLUMNS)].copy()
    validated["city_id"] = validated["city_id"].astype("string")
    validated["month"] = pd.to_numeric(validated["month"], errors="coerce")
    validated["normal_temperature_2m_max"] = pd.to_numeric(
        validated["normal_temperature_2m_max"],
        errors="coerce",
    )
    if validated.duplicated(["city_id", "month"]).any():
        duplicates = validated.loc[
            validated.duplicated(["city_id", "month"], keep=False),
            ["city_id", "month"],
        ]
        raise ValueError(
            "City monthly Heat normals contain duplicate city/month keys: "
            f"{duplicates.drop_duplicates().to_dict(orient='records')}"
        )
    if (
        validated["month"].isna().any()
        or not validated["month"]
        .map(lambda value: float(value).is_integer())
        .all()
        or not validated["month"].between(1, 12).all()
        or not np.isfinite(
            validated["normal_temperature_2m_max"].to_numpy(dtype=float)
        ).all()
    ):
        raise ValueError("City monthly Heat normals contain invalid month or value data")
    validated["month"] = validated["month"].astype(int)

    expected_keys = pd.MultiIndex.from_product(
        [ALL_CITIES, range(1, 13)],
        names=["city_id", "month"],
    )
    actual_keys = pd.MultiIndex.from_frame(validated[["city_id", "month"]])
    missing_keys = expected_keys.difference(actual_keys)
    if len(missing_keys):
        raise ValueError(
            "City monthly Heat normals are missing city/month keys: "
            f"{list(missing_keys[:10])}"
        )
    return validated


def target_date_heat_normals(
    evaluation_rows: pd.DataFrame,
    horizon_days: int,
    city_monthly_normals: pd.DataFrame,
) -> np.ndarray:
    """Resolve target-date-month normals without changing the model features."""

    if horizon_days not in FORECAST_HORIZONS:
        raise ValueError(
            f"Unsupported forecast horizon {horizon_days}; expected one of "
            f"{FORECAST_HORIZONS}"
        )
    required_context = ("city_id", "forecast_origin_date")
    missing_context = [
        column for column in required_context if column not in evaluation_rows
    ]
    if missing_context:
        raise ValueError(
            "Rule baseline evaluation context is missing: "
            + ", ".join(missing_context)
        )
    if city_monthly_normals.duplicated(["city_id", "month"]).any():
        raise ValueError("City monthly Heat normal lookup keys must be unique")

    context = evaluation_rows.loc[:, list(required_context)].copy()
    context["_row_order"] = np.arange(len(context))
    origin_dates = pd.to_datetime(
        context["forecast_origin_date"],
        errors="raise",
    )
    context["month"] = (
        origin_dates + pd.Timedelta(horizon_days, unit="D")
    ).dt.month
    merged = context.merge(
        city_monthly_normals.loc[:, list(NORMAL_COLUMNS)],
        how="left",
        on=["city_id", "month"],
        validate="many_to_one",
        sort=False,
    ).sort_values("_row_order")
    normal_values = pd.to_numeric(
        merged["normal_temperature_2m_max"],
        errors="coerce",
    ).to_numpy(dtype=float)
    if len(normal_values) != len(evaluation_rows) or not np.isfinite(
        normal_values
    ).all():
        missing_keys = merged.loc[
            ~np.isfinite(normal_values),
            ["city_id", "month"],
        ]
        raise ValueError(
            "Target-date Heat normal lookup is incomplete: "
            f"{missing_keys.drop_duplicates().to_dict(orient='records')}"
        )
    return normal_values


def same_vintage_rule_predictions(
    features: pd.DataFrame,
    horizon_days: int,
    *,
    target_normal_temperature: np.ndarray | pd.Series,
) -> np.ndarray:
    """Return deterministic Heat/Rain scores for the supplied forecast rows.

    Heat uses the selected horizon's forecast maximum, the following forecast
    day's maximum, and the normal for the *target date's* city/month. Rain uses
    the selected horizon's forecast precipitation. Both match the operational
    score formulas and are clipped and rounded to the public 0--100 contract.
    """

    if horizon_days not in FORECAST_HORIZONS:
        raise ValueError(
            f"Unsupported forecast horizon {horizon_days}; expected one of "
            f"{FORECAST_HORIZONS}"
        )

    required_columns = (
        f"temp_forecast_plus_{horizon_days}d",
        f"temp_forecast_plus_{horizon_days + 1}d",
        f"precip_forecast_plus_{horizon_days}d",
    )
    missing_columns = [
        column for column in required_columns if column not in features.columns
    ]
    if missing_columns:
        raise ValueError(
            "Rule baseline is missing same-vintage features: "
            + ", ".join(missing_columns)
        )

    numeric = features.loc[:, list(required_columns)].apply(
        pd.to_numeric,
        errors="coerce",
    )
    values = numeric.to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError(
            "Rule baseline requires complete finite same-vintage Heat/Rain inputs"
        )

    normal_temperature = np.asarray(target_normal_temperature, dtype=float)
    if normal_temperature.shape != (len(features),) or not np.isfinite(
        normal_temperature
    ).all():
        raise ValueError(
            "Rule baseline requires one finite target-date Heat normal per row"
        )
    temperature = numeric[
        f"temp_forecast_plus_{horizon_days}d"
    ].to_numpy()
    next_temperature = numeric[
        f"temp_forecast_plus_{horizon_days + 1}d"
    ].to_numpy()
    precipitation = numeric[
        f"precip_forecast_plus_{horizon_days}d"
    ].to_numpy()

    heat_score = (
        (temperature - normal_temperature) * 5.0
        + np.maximum(0.0, next_temperature - temperature) * 5.0
    )
    rain_score = precipitation * 2.0
    predictions = np.column_stack((heat_score, rain_score))
    return np.round(np.clip(predictions, 0.0, 100.0), 1)
