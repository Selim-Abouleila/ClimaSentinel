#!/usr/bin/env python3
"""Generate deterministic monthly climate normals from Open-Meteo archive data.

The script reads city coordinates and IANA timezones from ``config/cities.csv``.
It never edits the checked-in dbt seed in place: write the generated cohort to a
temporary file, review the accompanying metadata, and merge the rows explicitly.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CITIES_PATH = REPO_ROOT / "config" / "cities.csv"
CANONICAL_SEED_PATH = REPO_ROOT / "transform" / "seeds" / "city_monthly_normals.csv"
CANONICAL_PROVENANCE_PATH = (
    REPO_ROOT / "transform" / "seeds" / "city_monthly_normals.provenance.json"
)
SOURCE_ENDPOINT = "https://archive-api.open-meteo.com/v1/archive"
SOURCE_DOCUMENTATION = "https://open-meteo.com/en/docs/historical-weather-api"
SOURCE_CITATION = "https://doi.org/10.5281/ZENODO.7970649"
MODEL_SELECTOR = "best_match"
START_DATE = date(2014, 1, 1)
END_DATE = date(2023, 12, 31)
BATCH_SIZE = 10

CITY_COLUMNS = (
    "city_id",
    "city_name",
    "country_code",
    "latitude",
    "longitude",
    "timezone",
    "region",
    "active",
    "river_enabled",
    "display_order",
)
OUTPUT_COLUMNS = (
    "city_id",
    "month",
    "normal_temperature_2m_mean",
    "normal_temperature_2m_max",
    "normal_daily_precipitation_mm",
    "normal_wind_speed_10m_max",
)
VARIABLES = (
    ("normal_temperature_2m_mean", "temperature_2m_mean"),
    ("normal_temperature_2m_max", "temperature_2m_max"),
    ("normal_daily_precipitation_mm", "precipitation_sum"),
    ("normal_wind_speed_10m_max", "wind_speed_10m_max"),
)


class GenerationError(RuntimeError):
    """Raised when source data cannot satisfy the normal-generation contract."""


def _validate_output_paths(
    output_path: Path | None,
    metadata_output_path: Path | None,
) -> None:
    """Protect reviewed seed artifacts from direct generator overwrites."""

    protected_paths = {
        CANONICAL_SEED_PATH.resolve(): "checked-in monthly-normal seed",
        CANONICAL_PROVENANCE_PATH.resolve(): "checked-in provenance manifest",
    }
    for option, candidate in (
        ("--output", output_path),
        ("--metadata-output", metadata_output_path),
    ):
        if candidate is None:
            continue
        protected_label = protected_paths.get(candidate.resolve())
        if protected_label is not None:
            raise GenerationError(
                f"{option} cannot overwrite the {protected_label}; generate into a "
                "temporary file, review it, and merge intentionally"
            )


def _load_cities(path: Path, selected_city_ids: list[str]) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != CITY_COLUMNS:
            raise GenerationError(
                f"{path} columns must be exactly {CITY_COLUMNS}, got "
                f"{tuple(reader.fieldnames or ())}"
            )
        rows = list(reader)

    by_id: dict[str, dict[str, str]] = {}
    for row in rows:
        city_id = row["city_id"]
        if city_id in by_id:
            raise GenerationError(f"Duplicate city_id in {path}: {city_id}")
        try:
            latitude = float(row["latitude"])
            longitude = float(row["longitude"])
            display_order = int(row["display_order"])
        except ValueError as exc:
            raise GenerationError(f"Invalid numeric city field for {city_id}: {exc}") from exc
        if not math.isfinite(latitude) or not -90 <= latitude <= 90:
            raise GenerationError(f"Invalid latitude for {city_id}: {row['latitude']}")
        if not math.isfinite(longitude) or not -180 <= longitude <= 180:
            raise GenerationError(f"Invalid longitude for {city_id}: {row['longitude']}")
        if display_order < 1:
            raise GenerationError(f"Invalid display_order for {city_id}: {display_order}")
        by_id[city_id] = row

    if selected_city_ids:
        if len(selected_city_ids) != len(set(selected_city_ids)):
            raise GenerationError("Each --city-id may be specified only once")
        unknown = sorted(set(selected_city_ids) - set(by_id))
        if unknown:
            raise GenerationError(f"Unknown --city-id values: {unknown}")
        selected = set(selected_city_ids)
        rows = [row for row in rows if row["city_id"] in selected]
    else:
        rows = [row for row in rows if row["active"] == "true"]

    rows.sort(key=lambda row: int(row["display_order"]))
    if not rows:
        raise GenerationError("No cities selected")
    return rows


def _expected_dates() -> list[str]:
    values: list[str] = []
    current = START_DATE
    while current <= END_DATE:
        values.append(current.isoformat())
        current += timedelta(days=1)
    return values


def _request_batch(cities: list[dict[str, str]], max_attempts: int) -> list[dict[str, Any]]:
    params = {
        "latitude": ",".join(city["latitude"] for city in cities),
        "longitude": ",".join(city["longitude"] for city in cities),
        "start_date": START_DATE.isoformat(),
        "end_date": END_DATE.isoformat(),
        "daily": ",".join(api_name for _, api_name in VARIABLES),
        "timezone": ",".join(city["timezone"] for city in cities),
        "models": MODEL_SELECTOR,
        "temperature_unit": "celsius",
        "precipitation_unit": "mm",
        "wind_speed_unit": "kmh",
        "timeformat": "iso8601",
        "cell_selection": "land",
    }
    url = f"{SOURCE_ENDPOINT}?{urlencode(params)}"
    request = Request(
        url,
        headers={"User-Agent": "ClimaSentinel-monthly-normals-generator/1.0"},
    )

    for attempt in range(1, max_attempts + 1):
        try:
            with urlopen(request, timeout=240) as response:
                payload = json.load(response)
            break
        except HTTPError as exc:
            retryable = exc.code == 429 or 500 <= exc.code < 600
            if not retryable or attempt == max_attempts:
                body = exc.read().decode("utf-8", errors="replace")
                raise GenerationError(
                    f"Open-Meteo request failed with HTTP {exc.code}: {body}"
                ) from exc
        except (URLError, TimeoutError) as exc:
            if attempt == max_attempts:
                raise GenerationError(f"Open-Meteo request failed: {exc}") from exc

        delay_seconds = min(60, 5 * (2 ** (attempt - 1)))
        print(
            f"Open-Meteo request attempt {attempt} failed; retrying in "
            f"{delay_seconds}s",
            file=sys.stderr,
        )
        time.sleep(delay_seconds)
    else:  # pragma: no cover - loop either succeeds or raises
        raise GenerationError("Open-Meteo request exhausted all attempts")

    responses = payload if isinstance(payload, list) else [payload]
    if len(responses) != len(cities):
        raise GenerationError(
            f"Open-Meteo returned {len(responses)} locations for {len(cities)} requests"
        )
    if not all(isinstance(item, dict) for item in responses):
        raise GenerationError("Open-Meteo response contains a non-object location")
    return responses


def _decimal_mean(values: list[float]) -> Decimal:
    total = sum(Decimal(str(value)) for value in values)
    return (total / Decimal(len(values))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _format_decimal(value: Decimal) -> str:
    text = format(value, ".2f")
    if text.endswith("00"):
        return text[:-1]
    if text.endswith("0"):
        return text[:-1]
    return text


def _aggregate_city(
    city: dict[str, str],
    response: dict[str, Any],
    expected_dates: list[str],
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    if response.get("error"):
        raise GenerationError(
            f"Open-Meteo error for {city['city_id']}: {response.get('reason', response)}"
        )
    daily = response.get("daily")
    if not isinstance(daily, dict):
        raise GenerationError(f"Missing daily payload for {city['city_id']}")
    if daily.get("time") != expected_dates:
        raise GenerationError(
            f"Date coverage mismatch for {city['city_id']}; expected "
            f"{expected_dates[0]}..{expected_dates[-1]} ({len(expected_dates)} days)"
        )

    by_month: dict[int, dict[str, list[float]]] = {
        month: {api_name: [] for _, api_name in VARIABLES}
        for month in range(1, 13)
    }
    for index, date_text in enumerate(expected_dates):
        month = int(date_text[5:7])
        for _, api_name in VARIABLES:
            series = daily.get(api_name)
            if not isinstance(series, list) or len(series) != len(expected_dates):
                raise GenerationError(
                    f"Invalid {api_name} series length for {city['city_id']}"
                )
            value = series[index]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise GenerationError(
                    f"Missing/non-numeric {api_name} for {city['city_id']} on {date_text}"
                )
            numeric = float(value)
            if not math.isfinite(numeric):
                raise GenerationError(
                    f"Non-finite {api_name} for {city['city_id']} on {date_text}"
                )
            by_month[month][api_name].append(numeric)

    rows: list[dict[str, str]] = []
    month_counts: dict[str, int] = {}
    for month in range(1, 13):
        expected_count = sum(1 for value in expected_dates if int(value[5:7]) == month)
        month_counts[str(month)] = expected_count
        row = {"city_id": city["city_id"], "month": str(month)}
        for output_name, api_name in VARIABLES:
            values = by_month[month][api_name]
            if len(values) != expected_count:
                raise GenerationError(
                    f"Incomplete month {month} {api_name} for {city['city_id']}: "
                    f"{len(values)} of {expected_count} values"
                )
            row[output_name] = _format_decimal(_decimal_mean(values))
        rows.append(row)

    response_timezone = response.get("timezone")
    if response_timezone != city["timezone"]:
        raise GenerationError(
            f"Timezone mismatch for {city['city_id']}: requested {city['timezone']}, "
            f"received {response_timezone}"
        )
    metadata = {
        "city_id": city["city_id"],
        "requested": {
            "latitude": float(city["latitude"]),
            "longitude": float(city["longitude"]),
            "timezone": city["timezone"],
        },
        "returned": {
            "latitude": response.get("latitude"),
            "longitude": response.get("longitude"),
            "elevation_m": response.get("elevation"),
            "timezone": response_timezone,
            "utc_offset_seconds": response.get("utc_offset_seconds"),
        },
        "daily_row_count": len(expected_dates),
        "daily_rows_by_month": month_counts,
    }
    return rows, metadata


def generate(
    cities: list[dict[str, str]],
    *,
    batch_size: int,
    max_attempts: int,
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    expected_dates = _expected_dates()
    output_rows: list[dict[str, str]] = []
    response_metadata: list[dict[str, Any]] = []
    for start in range(0, len(cities), batch_size):
        batch = cities[start : start + batch_size]
        responses = _request_batch(batch, max_attempts=max_attempts)
        for city, response in zip(batch, responses, strict=True):
            rows, metadata = _aggregate_city(city, response, expected_dates)
            output_rows.extend(rows)
            response_metadata.append(metadata)
    return output_rows, response_metadata


def _render_csv(rows: list[dict[str, str]]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=OUTPUT_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def _build_metadata(
    *,
    generated_at_utc: str,
    cities_path: Path,
    selected_cities: list[dict[str, str]],
    response_metadata: list[dict[str, Any]],
    csv_text: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "generated_at_utc": generated_at_utc,
        "generator": "transform/scripts/generate_city_monthly_normals.py",
        "source": {
            "provider": "Open-Meteo Historical Weather API",
            "endpoint": SOURCE_ENDPOINT,
            "documentation": SOURCE_DOCUMENTATION,
            "citation": SOURCE_CITATION,
            "model_selector": MODEL_SELECTOR,
            "period": {
                "start_date": START_DATE.isoformat(),
                "end_date": END_DATE.isoformat(),
            },
            "daily_variables": [api_name for _, api_name in VARIABLES],
            "timezone": "Per-city IANA timezone from config/cities.csv",
            "units": {
                "temperature": "celsius",
                "precipitation": "mm",
                "wind_speed": "km/h",
            },
            "timeformat": "iso8601",
            "cell_selection": "land",
        },
        "method": {
            "aggregation": (
                "Arithmetic mean of every daily value in the 2014-2023 period, "
                "grouped by local calendar month"
            ),
            "missing_data_policy": (
                "Fail generation if any requested day or variable is missing, "
                "non-numeric, or non-finite"
            ),
            "rounding": "Decimal ROUND_HALF_UP to two decimal places",
        },
        "city_registry": str(cities_path.resolve().relative_to(REPO_ROOT)),
        "selected_city_ids": [city["city_id"] for city in selected_cities],
        "responses": response_metadata,
        "output": {
            "row_count": len(selected_cities) * 12,
            "sha256": hashlib.sha256(csv_text.encode("utf-8")).hexdigest(),
        },
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cities", type=Path, default=DEFAULT_CITIES_PATH)
    parser.add_argument(
        "--city-id",
        action="append",
        default=[],
        help="Generate one registered city (repeatable); defaults to all active cities.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write generated CSV here; defaults to stdout.",
    )
    parser.add_argument(
        "--metadata-output",
        type=Path,
        help="Optionally write request, response-grid, and checksum metadata as JSON.",
    )
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    parser.add_argument("--max-attempts", type=int, default=4)
    parser.add_argument(
        "--generated-at-utc",
        help="Metadata timestamp override (ISO 8601); defaults to the current UTC time.",
    )
    args = parser.parse_args(argv)
    if args.batch_size < 1 or args.batch_size > 10:
        parser.error("--batch-size must be between 1 and 10")
    if args.max_attempts < 1:
        parser.error("--max-attempts must be at least 1")
    return args


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    generated_at_utc = args.generated_at_utc or datetime.now(timezone.utc).replace(
        microsecond=0
    ).isoformat().replace("+00:00", "Z")
    try:
        _validate_output_paths(args.output, args.metadata_output)
        cities = _load_cities(args.cities, args.city_id)
        rows, response_metadata = generate(
            cities,
            batch_size=args.batch_size,
            max_attempts=args.max_attempts,
        )
        csv_text = _render_csv(rows)
        metadata = _build_metadata(
            generated_at_utc=generated_at_utc,
            cities_path=args.cities,
            selected_cities=cities,
            response_metadata=response_metadata,
            csv_text=csv_text,
        )
    except (GenerationError, OSError, ValueError) as exc:
        print(f"Normal generation failed: {exc}", file=sys.stderr)
        return 1

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(csv_text, encoding="utf-8")
    else:
        sys.stdout.write(csv_text)
    if args.metadata_output:
        args.metadata_output.parent.mkdir(parents=True, exist_ok=True)
        args.metadata_output.write_text(
            json.dumps(metadata, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(
        f"Generated {len(rows)} rows for {len(cities)} cities; "
        f"sha256={metadata['output']['sha256']}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
