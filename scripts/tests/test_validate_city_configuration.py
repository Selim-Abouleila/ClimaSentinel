from __future__ import annotations

import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.validate_city_configuration import (
    CITIES_COLUMNS,
    EXPECTED_FORECAST_CITIES,
    FORECAST_ALLOWLIST_COLUMNS,
    NORMALS_COLUMNS,
    SIGNAL_MONITORING_COLUMNS,
    validate_city_configuration,
)


class CityConfigurationValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.cities_path = self.root / "cities.csv"
        self.normals_path = self.root / "normals.csv"
        self.provenance_path = self.root / "normals.provenance.json"
        self.allowlist_path = self.root / "allowlist.csv"
        self.monitoring_path = self.root / "signal_monitoring.csv"
        self.city_rows = []
        for display_order, (city_id, timezone) in enumerate(
            EXPECTED_FORECAST_CITIES.items(), start=1
        ):
            country_code = city_id.rsplit("_", 1)[1].upper()
            self.city_rows.append(
                {
                    "city_id": city_id,
                    "city_name": city_id.split("_", 1)[0].title(),
                    "country_code": country_code,
                    "latitude": "45.0",
                    "longitude": "5.0",
                    "timezone": timezone,
                    "region": "Test Region",
                    "active": "true",
                    "river_enabled": "false",
                    "display_order": str(display_order),
                }
            )
        self.normal_rows = [
            {
                "city_id": city["city_id"],
                "month": str(month),
                "normal_temperature_2m_mean": "12.0",
                "normal_temperature_2m_max": "18.0",
                "normal_daily_precipitation_mm": "2.0",
                "normal_wind_speed_10m_max": "20.0",
            }
            for city in self.city_rows
            for month in range(1, 13)
        ]
        self.allowlist_rows = [
            {"city_id": city_id, "forecast_origin_time_zone": timezone}
            for city_id, timezone in EXPECTED_FORECAST_CITIES.items()
        ]
        self.monitoring_rows = [
            {
                "city_id": city["city_id"],
                "heat_monitored": "true",
                "wind_monitored": "true",
                "rain_monitored": "true",
                "air_monitored": "true",
                "river_monitored": city["river_enabled"],
            }
            for city in self.city_rows
        ]

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    @staticmethod
    def _write_csv(path: Path, columns: tuple[str, ...], rows: list[dict[str, str]]) -> None:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)

    def _validate(self) -> list[str]:
        self._write_csv(self.cities_path, CITIES_COLUMNS, self.city_rows)
        self._write_csv(self.normals_path, NORMALS_COLUMNS, self.normal_rows)
        self._write_csv(
            self.allowlist_path,
            FORECAST_ALLOWLIST_COLUMNS,
            self.allowlist_rows,
        )
        self._write_csv(
            self.monitoring_path,
            SIGNAL_MONITORING_COLUMNS,
            self.monitoring_rows,
        )
        normal_rows = self.normals_path.read_bytes()
        self.provenance_path.write_text(
            json.dumps(
                {
                    "checked_in_snapshot": {
                        "city_count": len({row["city_id"] for row in self.normal_rows}),
                        "row_count": len(self.normal_rows),
                        "sha256": hashlib.sha256(normal_rows).hexdigest(),
                    }
                }
            ),
            encoding="utf-8",
        )
        return validate_city_configuration(
            self.cities_path,
            self.normals_path,
            self.allowlist_path,
            self.provenance_path,
            self.monitoring_path,
        )

    def test_accepts_complete_configuration(self) -> None:
        self.assertEqual(self._validate(), [])

    def test_rejects_invalid_city_fields_and_duplicate_display_order(self) -> None:
        self.city_rows[0]["latitude"] = "91"
        self.city_rows[0]["active"] = "TRUE"
        self.city_rows[1]["timezone"] = "Not/A_Timezone"
        self.city_rows[1]["display_order"] = self.city_rows[0]["display_order"]

        errors = "\n".join(self._validate())

        self.assertIn("latitude must be between -90 and 90", errors)
        self.assertIn("active must be exactly 'true' or 'false'", errors)
        self.assertIn("must be a valid IANA timezone", errors)
        self.assertIn("duplicate display_order", errors)

    def test_rejects_incomplete_duplicate_and_nonphysical_normals(self) -> None:
        removed = self.normal_rows.pop(0)
        duplicate = dict(self.normal_rows[0])
        duplicate["normal_temperature_2m_max"] = "nan"
        self.normal_rows.append(duplicate)

        errors = "\n".join(self._validate())

        self.assertIn(f"duplicate city/month key {(duplicate['city_id'], 2)!r}", errors)
        self.assertIn("normal_temperature_2m_max must be finite", errors)
        self.assertIn("missing=[1]", errors)
        self.assertEqual(removed["month"], "1")

    def test_rejects_forecast_allowlist_scope_change(self) -> None:
        self.allowlist_rows.pop()
        self.allowlist_rows.append(
            {
                "city_id": "vienna_at",
                "forecast_origin_time_zone": "Europe/Vienna",
            }
        )

        errors = "\n".join(self._validate())

        self.assertIn("frozen forecast allowlist is missing city IDs", errors)
        self.assertIn("frozen forecast allowlist has unexpected city IDs", errors)

    def test_rejects_monitoring_seed_drift(self) -> None:
        removed = self.monitoring_rows.pop()
        self.city_rows[0]["river_enabled"] = "true"
        self.monitoring_rows[0]["heat_monitored"] = "false"

        errors = "\n".join(self._validate())

        self.assertIn("monitoring seed is missing active city IDs", errors)
        self.assertIn(removed["city_id"], errors)
        self.assertIn("heat_monitored", errors)
        self.assertIn("river_monitored", errors)
        self.assertIn("to match the ingestion contract", errors)

    def test_rejects_duplicate_invalid_and_unknown_monitoring_rows(self) -> None:
        duplicate = dict(self.monitoring_rows[0])
        self.monitoring_rows.append(duplicate)
        self.monitoring_rows[1]["air_monitored"] = "TRUE"
        unknown = dict(self.monitoring_rows[2])
        unknown["city_id"] = "unknown_xx"
        self.monitoring_rows.append(unknown)

        errors = "\n".join(self._validate())

        self.assertIn(f"duplicate city_id {duplicate['city_id']!r}", errors)
        self.assertIn("air_monitored must be exactly 'true' or 'false'", errors)
        self.assertIn("monitoring city 'unknown_xx' is not registered", errors)
        self.assertIn("monitoring seed has non-active or unknown city IDs", errors)

    def test_rejects_stale_normals_provenance(self) -> None:
        self._write_csv(self.cities_path, CITIES_COLUMNS, self.city_rows)
        self._write_csv(self.normals_path, NORMALS_COLUMNS, self.normal_rows)
        self._write_csv(
            self.allowlist_path,
            FORECAST_ALLOWLIST_COLUMNS,
            self.allowlist_rows,
        )
        self._write_csv(
            self.monitoring_path,
            SIGNAL_MONITORING_COLUMNS,
            self.monitoring_rows,
        )
        self.provenance_path.write_text(
            json.dumps(
                {
                    "checked_in_snapshot": {
                        "city_count": 10,
                        "row_count": 120,
                        "sha256": "0" * 64,
                    }
                }
            ),
            encoding="utf-8",
        )

        errors = "\n".join(
            validate_city_configuration(
                self.cities_path,
                self.normals_path,
                self.allowlist_path,
                self.provenance_path,
                self.monitoring_path,
            )
        )

        self.assertIn("checked_in_snapshot.sha256 must match", errors)


if __name__ == "__main__":
    unittest.main()
