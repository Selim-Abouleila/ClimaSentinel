#!/usr/bin/env python3
"""Validate the operational and forecast city configuration contracts.

The validator deliberately uses only the Python standard library so it can run
before application or dbt dependencies are installed. It validates the source
files that are copied into the ingestion image and seeded into BigQuery.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CITIES_PATH = REPO_ROOT / "config" / "cities.csv"
DEFAULT_NORMALS_PATH = REPO_ROOT / "transform" / "seeds" / "city_monthly_normals.csv"
DEFAULT_NORMALS_PROVENANCE_PATH = (
    REPO_ROOT / "transform" / "seeds" / "city_monthly_normals.provenance.json"
)
DEFAULT_FORECAST_ALLOWLIST_PATH = (
    REPO_ROOT / "transform" / "seeds" / "forecast_city_allowlist.csv"
)
DEFAULT_SIGNAL_MONITORING_PATH = (
    REPO_ROOT / "transform" / "seeds" / "city_signal_monitoring.csv"
)

CITIES_COLUMNS = (
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
NORMALS_COLUMNS = (
    "city_id",
    "month",
    "normal_temperature_2m_mean",
    "normal_temperature_2m_max",
    "normal_daily_precipitation_mm",
    "normal_wind_speed_10m_max",
)
FORECAST_ALLOWLIST_COLUMNS = ("city_id", "forecast_origin_time_zone")
SIGNAL_MONITORING_COLUMNS = (
    "city_id",
    "heat_monitored",
    "wind_monitored",
    "rain_monitored",
    "air_monitored",
    "river_monitored",
)

# This contract intentionally keeps operational city expansion out of the
# point-in-time forecast, training, and serving path.
EXPECTED_FORECAST_CITIES = {
    "paris_fr": "Europe/Paris",
    "london_gb": "Europe/London",
    "madrid_es": "Europe/Madrid",
    "berlin_de": "Europe/Berlin",
    "rome_it": "Europe/Rome",
    "amsterdam_nl": "Europe/Amsterdam",
    "athens_gr": "Europe/Athens",
    "warsaw_pl": "Europe/Warsaw",
    "lisbon_pt": "Europe/Lisbon",
    "stockholm_se": "Europe/Stockholm",
}

CITY_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*_[a-z]{2}$")
COUNTRY_CODE_PATTERN = re.compile(r"^[A-Z]{2}$")
POSITIVE_INTEGER_PATTERN = re.compile(r"^[1-9][0-9]*$")
MONTHS = frozenset(range(1, 13))
STRICT_BOOLEANS = frozenset({"true", "false"})

# Broad physical guardrails catch missing signs, swapped units, and corrupt
# seed values without rejecting plausible European climate normals.
NORMAL_RANGES = {
    "normal_temperature_2m_mean": (-80.0, 60.0),
    "normal_temperature_2m_max": (-80.0, 70.0),
    "normal_daily_precipitation_mm": (0.0, 100.0),
    "normal_wind_speed_10m_max": (0.0, 250.0),
}


def _load_csv(
    path: Path,
    expected_columns: tuple[str, ...],
    errors: list[str],
) -> list[tuple[int, dict[str, str]]]:
    """Load and normalize a CSV while preserving source line numbers."""

    try:
        handle = path.open("r", encoding="utf-8-sig", newline="")
    except OSError as exc:
        errors.append(f"{path}: cannot read file: {exc}")
        return []

    with handle:
        reader = csv.DictReader(handle)
        actual_columns = tuple(reader.fieldnames or ())
        if actual_columns != expected_columns:
            errors.append(
                f"{path}: expected columns {expected_columns}, got {actual_columns}"
            )
            return []

        rows: list[tuple[int, dict[str, str]]] = []
        for line_number, raw_row in enumerate(reader, start=2):
            if None in raw_row:
                errors.append(f"{path}:{line_number}: row has more fields than the header")
                continue

            row: dict[str, str] = {}
            for column in expected_columns:
                raw_value = raw_row.get(column)
                value = "" if raw_value is None else raw_value
                stripped = value.strip()
                if value != stripped:
                    errors.append(
                        f"{path}:{line_number}: {column} has surrounding whitespace"
                    )
                if not stripped:
                    errors.append(f"{path}:{line_number}: {column} must not be empty")
                row[column] = stripped
            rows.append((line_number, row))

    if not rows:
        errors.append(f"{path}: must contain at least one data row")
    return rows


def _parse_finite_float(
    value: str,
    *,
    path: Path,
    line_number: int,
    column: str,
    errors: list[str],
) -> float | None:
    try:
        parsed = float(value)
    except ValueError:
        errors.append(f"{path}:{line_number}: {column} must be numeric, got {value!r}")
        return None
    if not math.isfinite(parsed):
        errors.append(f"{path}:{line_number}: {column} must be finite, got {value!r}")
        return None
    return parsed


def _validate_timezone(
    value: str,
    *,
    path: Path,
    line_number: int,
    column: str,
    errors: list[str],
) -> None:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        errors.append(
            f"{path}:{line_number}: {column} must be a valid IANA timezone, got {value!r}"
        )


def validate_cities(
    path: Path,
    errors: list[str],
) -> dict[str, dict[str, str]]:
    rows = _load_csv(path, CITIES_COLUMNS, errors)
    cities: dict[str, dict[str, str]] = {}
    city_lines: dict[str, int] = {}
    display_order_lines: dict[int, int] = {}

    for line_number, row in rows:
        city_id = row["city_id"]
        country_code = row["country_code"]

        if not CITY_ID_PATTERN.fullmatch(city_id):
            errors.append(
                f"{path}:{line_number}: city_id must be lowercase snake_case with a "
                f"two-letter country suffix, got {city_id!r}"
            )
        if not city_id.endswith(f"_{country_code.lower()}"):
            errors.append(
                f"{path}:{line_number}: city_id {city_id!r} must end with the lowercase "
                f"country_code suffix _{country_code.lower()}"
            )
        if not COUNTRY_CODE_PATTERN.fullmatch(country_code):
            errors.append(
                f"{path}:{line_number}: country_code must contain two uppercase letters, "
                f"got {country_code!r}"
            )

        if city_id in city_lines:
            errors.append(
                f"{path}:{line_number}: duplicate city_id {city_id!r}; first seen on "
                f"line {city_lines[city_id]}"
            )
        else:
            city_lines[city_id] = line_number
            cities[city_id] = row

        latitude = _parse_finite_float(
            row["latitude"],
            path=path,
            line_number=line_number,
            column="latitude",
            errors=errors,
        )
        longitude = _parse_finite_float(
            row["longitude"],
            path=path,
            line_number=line_number,
            column="longitude",
            errors=errors,
        )
        if latitude is not None and not -90.0 <= latitude <= 90.0:
            errors.append(f"{path}:{line_number}: latitude must be between -90 and 90")
        if longitude is not None and not -180.0 <= longitude <= 180.0:
            errors.append(f"{path}:{line_number}: longitude must be between -180 and 180")

        _validate_timezone(
            row["timezone"],
            path=path,
            line_number=line_number,
            column="timezone",
            errors=errors,
        )

        for column in ("active", "river_enabled"):
            if row[column] not in STRICT_BOOLEANS:
                errors.append(
                    f"{path}:{line_number}: {column} must be exactly 'true' or 'false', "
                    f"got {row[column]!r}"
                )

        display_order_text = row["display_order"]
        if not POSITIVE_INTEGER_PATTERN.fullmatch(display_order_text):
            errors.append(
                f"{path}:{line_number}: display_order must be a positive integer, "
                f"got {display_order_text!r}"
            )
        else:
            display_order = int(display_order_text)
            if display_order in display_order_lines:
                errors.append(
                    f"{path}:{line_number}: duplicate display_order {display_order}; first "
                    f"seen on line {display_order_lines[display_order]}"
                )
            else:
                display_order_lines[display_order] = line_number

    return cities


def validate_normals(
    path: Path,
    cities: dict[str, dict[str, str]],
    errors: list[str],
) -> None:
    rows = _load_csv(path, NORMALS_COLUMNS, errors)
    key_lines: dict[tuple[str, int], int] = {}
    observed_months: dict[str, list[int]] = defaultdict(list)

    for line_number, row in rows:
        city_id = row["city_id"]
        if city_id not in cities:
            errors.append(
                f"{path}:{line_number}: city_id {city_id!r} is not registered in config/cities.csv"
            )

        month: int | None = None
        try:
            month = int(row["month"])
        except ValueError:
            errors.append(
                f"{path}:{line_number}: month must be an integer from 1 through 12, "
                f"got {row['month']!r}"
            )
        if month is not None:
            if month not in MONTHS:
                errors.append(f"{path}:{line_number}: month must be between 1 and 12")
            key = (city_id, month)
            if key in key_lines:
                errors.append(
                    f"{path}:{line_number}: duplicate city/month key {key!r}; first seen "
                    f"on line {key_lines[key]}"
                )
            else:
                key_lines[key] = line_number
            observed_months[city_id].append(month)

        values: dict[str, float] = {}
        for column, (minimum, maximum) in NORMAL_RANGES.items():
            value = _parse_finite_float(
                row[column],
                path=path,
                line_number=line_number,
                column=column,
                errors=errors,
            )
            if value is None:
                continue
            values[column] = value
            if not minimum <= value <= maximum:
                errors.append(
                    f"{path}:{line_number}: {column} must be between {minimum:g} and "
                    f"{maximum:g}, got {value:g}"
                )

        mean_temperature = values.get("normal_temperature_2m_mean")
        max_temperature = values.get("normal_temperature_2m_max")
        if (
            mean_temperature is not None
            and max_temperature is not None
            and max_temperature < mean_temperature
        ):
            errors.append(
                f"{path}:{line_number}: normal_temperature_2m_max must be greater than "
                "or equal to normal_temperature_2m_mean"
            )

    for city_id, months in sorted(observed_months.items()):
        month_counts = Counter(months)
        if set(month_counts) != MONTHS or any(count != 1 for count in month_counts.values()):
            missing = sorted(MONTHS - set(month_counts))
            duplicate = sorted(month for month, count in month_counts.items() if count > 1)
            errors.append(
                f"{path}: city {city_id!r} must have exactly one row for every month "
                f"1-12 (missing={missing}, duplicate={duplicate})"
            )

    for city_id, city in sorted(cities.items()):
        if city["active"] == "true" and city_id not in observed_months:
            errors.append(
                f"{path}: active city {city_id!r} has no monthly normals; expected months 1-12"
            )


def validate_forecast_allowlist(
    path: Path,
    cities: dict[str, dict[str, str]],
    errors: list[str],
) -> None:
    rows = _load_csv(path, FORECAST_ALLOWLIST_COLUMNS, errors)
    actual: dict[str, str] = {}
    city_lines: dict[str, int] = {}

    for line_number, row in rows:
        city_id = row["city_id"]
        timezone = row["forecast_origin_time_zone"]
        if city_id in city_lines:
            errors.append(
                f"{path}:{line_number}: duplicate city_id {city_id!r}; first seen on "
                f"line {city_lines[city_id]}"
            )
        else:
            city_lines[city_id] = line_number
            actual[city_id] = timezone

        _validate_timezone(
            timezone,
            path=path,
            line_number=line_number,
            column="forecast_origin_time_zone",
            errors=errors,
        )

        city = cities.get(city_id)
        if city is None:
            errors.append(
                f"{path}:{line_number}: forecast city {city_id!r} is not registered in "
                "config/cities.csv"
            )
        else:
            if city["active"] != "true":
                errors.append(
                    f"{path}:{line_number}: forecast city {city_id!r} must remain active"
                )
            if city["timezone"] != timezone:
                errors.append(
                    f"{path}:{line_number}: forecast timezone {timezone!r} does not match "
                    f"config timezone {city['timezone']!r} for {city_id!r}"
                )

    missing = sorted(set(EXPECTED_FORECAST_CITIES) - set(actual))
    unexpected = sorted(set(actual) - set(EXPECTED_FORECAST_CITIES))
    changed = sorted(
        city_id
        for city_id in set(actual) & set(EXPECTED_FORECAST_CITIES)
        if actual[city_id] != EXPECTED_FORECAST_CITIES[city_id]
    )
    if missing:
        errors.append(f"{path}: frozen forecast allowlist is missing city IDs: {missing}")
    if unexpected:
        errors.append(f"{path}: frozen forecast allowlist has unexpected city IDs: {unexpected}")
    for city_id in changed:
        errors.append(
            f"{path}: forecast timezone for {city_id!r} must remain "
            f"{EXPECTED_FORECAST_CITIES[city_id]!r}, got {actual[city_id]!r}"
        )


def validate_signal_monitoring(
    path: Path,
    cities: dict[str, dict[str, str]],
    errors: list[str],
) -> None:
    """Keep the dbt monitoring seed synchronized with the ingest registry."""

    rows = _load_csv(path, SIGNAL_MONITORING_COLUMNS, errors)
    actual: dict[str, dict[str, str]] = {}
    city_lines: dict[str, int] = {}

    for line_number, row in rows:
        city_id = row["city_id"]
        if city_id in city_lines:
            errors.append(
                f"{path}:{line_number}: duplicate city_id {city_id!r}; first seen on "
                f"line {city_lines[city_id]}"
            )
        else:
            city_lines[city_id] = line_number
            actual[city_id] = row

        for column in SIGNAL_MONITORING_COLUMNS[1:]:
            if row[column] not in STRICT_BOOLEANS:
                errors.append(
                    f"{path}:{line_number}: {column} must be exactly 'true' or 'false', "
                    f"got {row[column]!r}"
                )

        city = cities.get(city_id)
        if city is None:
            errors.append(
                f"{path}:{line_number}: monitoring city {city_id!r} is not registered "
                "in config/cities.csv"
            )
        elif city["active"] != "true":
            errors.append(
                f"{path}:{line_number}: monitoring city {city_id!r} must be active"
            )

    active_city_ids = {
        city_id for city_id, city in cities.items() if city["active"] == "true"
    }
    missing = sorted(active_city_ids - set(actual))
    unexpected = sorted(set(actual) - active_city_ids)
    if missing:
        errors.append(f"{path}: monitoring seed is missing active city IDs: {missing}")
    if unexpected:
        errors.append(
            f"{path}: monitoring seed has non-active or unknown city IDs: {unexpected}"
        )

    for city_id in sorted(active_city_ids & set(actual)):
        city = cities[city_id]
        row = actual[city_id]
        expected = {
            "heat_monitored": "true",
            "wind_monitored": "true",
            "rain_monitored": "true",
            "air_monitored": "true",
            "river_monitored": city["river_enabled"],
        }
        for column, expected_value in expected.items():
            if row[column] != expected_value:
                errors.append(
                    f"{path}:{city_lines[city_id]}: {column} for {city_id!r} must be "
                    f"{expected_value!r} to match the ingestion contract, got "
                    f"{row[column]!r}"
                )


def validate_normals_provenance(
    path: Path,
    normals_path: Path,
    errors: list[str],
) -> None:
    """Verify that snapshot counts and checksum describe the checked-in seed."""

    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        errors.append(f"{path}: cannot read file: {exc}")
        return
    except json.JSONDecodeError as exc:
        errors.append(f"{path}: invalid JSON: {exc}")
        return

    if not isinstance(document, dict):
        errors.append(f"{path}: top-level JSON value must be an object")
        return

    snapshot = document.get("checked_in_snapshot")
    if not isinstance(snapshot, dict):
        errors.append(f"{path}: checked_in_snapshot must be an object")
        return

    try:
        normals_bytes = normals_path.read_bytes()
    except OSError as exc:
        errors.append(f"{normals_path}: cannot calculate provenance checksum: {exc}")
        return

    try:
        with normals_path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except OSError as exc:
        errors.append(f"{normals_path}: cannot calculate provenance counts: {exc}")
        return

    actual = {
        "city_count": len({row.get("city_id", "") for row in rows}),
        "row_count": len(rows),
        "sha256": hashlib.sha256(normals_bytes).hexdigest(),
    }
    for field, actual_value in actual.items():
        recorded_value = snapshot.get(field)
        if recorded_value != actual_value:
            errors.append(
                f"{path}: checked_in_snapshot.{field} must match {normals_path}; "
                f"recorded={recorded_value!r}, actual={actual_value!r}"
            )


def validate_city_configuration(
    cities_path: Path = DEFAULT_CITIES_PATH,
    normals_path: Path = DEFAULT_NORMALS_PATH,
    forecast_allowlist_path: Path = DEFAULT_FORECAST_ALLOWLIST_PATH,
    normals_provenance_path: Path | None = DEFAULT_NORMALS_PROVENANCE_PATH,
    signal_monitoring_path: Path = DEFAULT_SIGNAL_MONITORING_PATH,
) -> list[str]:
    """Return all city configuration contract violations."""

    errors: list[str] = []
    cities = validate_cities(cities_path, errors)
    validate_normals(normals_path, cities, errors)
    validate_forecast_allowlist(forecast_allowlist_path, cities, errors)
    validate_signal_monitoring(signal_monitoring_path, cities, errors)
    if normals_provenance_path is not None:
        validate_normals_provenance(normals_provenance_path, normals_path, errors)
    return errors


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cities", type=Path, default=DEFAULT_CITIES_PATH)
    parser.add_argument("--normals", type=Path, default=DEFAULT_NORMALS_PATH)
    parser.add_argument(
        "--normals-provenance",
        type=Path,
        default=DEFAULT_NORMALS_PROVENANCE_PATH,
    )
    parser.add_argument(
        "--forecast-allowlist",
        type=Path,
        default=DEFAULT_FORECAST_ALLOWLIST_PATH,
    )
    parser.add_argument(
        "--signal-monitoring",
        type=Path,
        default=DEFAULT_SIGNAL_MONITORING_PATH,
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    errors = validate_city_configuration(
        cities_path=args.cities,
        normals_path=args.normals,
        forecast_allowlist_path=args.forecast_allowlist,
        normals_provenance_path=args.normals_provenance,
        signal_monitoring_path=args.signal_monitoring,
    )
    if errors:
        print(
            f"City configuration validation failed with {len(errors)} error(s):",
            file=sys.stderr,
        )
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    with args.cities.open("r", encoding="utf-8-sig", newline="") as handle:
        city_count = sum(1 for _ in csv.DictReader(handle))
    with args.normals.open("r", encoding="utf-8-sig", newline="") as handle:
        normal_count = sum(1 for _ in csv.DictReader(handle))
    with args.signal_monitoring.open(
        "r", encoding="utf-8-sig", newline=""
    ) as handle:
        monitoring_count = sum(1 for _ in csv.DictReader(handle))
    print(
        "City configuration is valid: "
        f"{city_count} registered cities, {normal_count} monthly normal rows, "
        f"{monitoring_count} monitoring contracts, "
        f"{len(EXPECTED_FORECAST_CITIES)} frozen forecast cities."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
