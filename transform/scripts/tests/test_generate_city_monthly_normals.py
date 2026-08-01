from __future__ import annotations

import unittest
from decimal import Decimal

from transform.scripts import generate_city_monthly_normals as normals


class MonthlyNormalGeneratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.dates = normals._expected_dates()
        cls.city = {
            "city_id": "test_xy",
            "latitude": "50.0",
            "longitude": "10.0",
            "timezone": "Europe/Berlin",
        }

    def _response(self) -> dict:
        row_count = len(self.dates)
        return {
            "latitude": 50.0,
            "longitude": 10.0,
            "elevation": 100.0,
            "timezone": "Europe/Berlin",
            "utc_offset_seconds": 7200,
            "daily": {
                "time": list(self.dates),
                "temperature_2m_mean": [1.25] * row_count,
                "temperature_2m_max": [2.5] * row_count,
                "precipitation_sum": [3.75] * row_count,
                "wind_speed_10m_max": [4.0] * row_count,
            },
        }

    def test_aggregates_one_complete_row_per_month(self) -> None:
        rows, metadata = normals._aggregate_city(
            self.city,
            self._response(),
            self.dates,
        )

        self.assertEqual(len(rows), 12)
        self.assertEqual(
            rows[0],
            {
                "city_id": "test_xy",
                "month": "1",
                "normal_temperature_2m_mean": "1.25",
                "normal_temperature_2m_max": "2.5",
                "normal_daily_precipitation_mm": "3.75",
                "normal_wind_speed_10m_max": "4.0",
            },
        )
        self.assertEqual(rows[-1]["month"], "12")
        self.assertEqual(metadata["daily_row_count"], 3652)
        self.assertEqual(metadata["daily_rows_by_month"]["2"], 282)

    def test_rejects_missing_daily_values(self) -> None:
        response = self._response()
        response["daily"]["precipitation_sum"][42] = None

        with self.assertRaisesRegex(normals.GenerationError, "Missing/non-numeric"):
            normals._aggregate_city(self.city, response, self.dates)

    def test_rounds_decimal_half_up_and_renders_unix_newlines(self) -> None:
        self.assertEqual(normals._decimal_mean([1.0, 1.01]), Decimal("1.01"))
        csv_text = normals._render_csv(
            [
                {
                    "city_id": "test_xy",
                    "month": "1",
                    "normal_temperature_2m_mean": "1.25",
                    "normal_temperature_2m_max": "2.5",
                    "normal_daily_precipitation_mm": "3.75",
                    "normal_wind_speed_10m_max": "4.0",
                }
            ]
        )
        self.assertTrue(csv_text.endswith("\n"))
        self.assertNotIn("\r\n", csv_text)

    def test_rejects_overwriting_checked_in_seed_artifacts(self) -> None:
        protected_options = (
            ("--output", normals.CANONICAL_SEED_PATH),
            ("--metadata-output", normals.CANONICAL_PROVENANCE_PATH),
        )
        for option, path in protected_options:
            with self.subTest(option=option):
                with self.assertRaisesRegex(
                    normals.GenerationError,
                    "cannot overwrite",
                ):
                    normals._validate_output_paths(
                        path if option == "--output" else None,
                        path if option == "--metadata-output" else None,
                    )


if __name__ == "__main__":
    unittest.main()
