from __future__ import annotations

import hashlib
import io
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

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
                "temperature_2m_min": [-1.25] * row_count,
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
                "normal_temperature_2m_min": "-1.25",
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
                    "normal_temperature_2m_min": "-1.25",
                    "normal_daily_precipitation_mm": "3.75",
                    "normal_wind_speed_10m_max": "4.0",
                }
            ]
        )
        self.assertTrue(csv_text.endswith("\n"))
        self.assertNotIn("\r\n", csv_text)

    def test_minimum_normal_averages_daily_lows_including_leap_days(self) -> None:
        response = self._response()
        # February has 282 observations: two leap days with -10 C, all others 0 C.
        response["daily"]["temperature_2m_min"] = [
            -10.0 if day in ("2016-02-29", "2020-02-29") else 0.0
            for day in self.dates
        ]
        rows, _ = normals._aggregate_city(self.city, response, self.dates)
        self.assertEqual(rows[1]["normal_temperature_2m_min"], "-0.07")
        self.assertEqual(rows[0]["normal_temperature_2m_min"], "0.0")

    def test_rejects_invalid_minimum_temperatures(self) -> None:
        for invalid in (None, float("nan"), float("inf"), True):
            with self.subTest(invalid=invalid):
                response = self._response()
                response["daily"]["temperature_2m_min"][42] = invalid
                with self.assertRaises(normals.GenerationError):
                    normals._aggregate_city(self.city, response, self.dates)

    def test_rejects_missing_day(self) -> None:
        response = self._response()
        response["daily"]["time"].pop()
        with self.assertRaisesRegex(normals.GenerationError, "Date coverage mismatch"):
            normals._aggregate_city(self.city, response, self.dates)

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

    def test_rate_limit_retry_waits_for_quota_window(self) -> None:
        for retry_after, expected_wait in ((None, 60), ("90", 90), ("invalid", 60)):
            with self.subTest(retry_after=retry_after):
                headers = {} if retry_after is None else {"Retry-After": retry_after}
                error = HTTPError("https://example.invalid", 429, "rate limited", headers, None)
                with patch.object(normals, "urlopen", side_effect=[error, io.StringIO("{}")]):
                    with patch.object(normals.time, "sleep") as sleep:
                        normals._request_batch([self.city], max_attempts=2)
                sleep.assert_called_once_with(expected_wait)

    def test_long_retry_after_fails_without_retrying_early(self) -> None:
        error = HTTPError(
            "https://example.invalid", 429, "rate limited", {"Retry-After": "900"}, None
        )
        with patch.object(normals, "urlopen", side_effect=error) as request:
            with patch.object(normals.time, "sleep") as sleep:
                with self.assertRaisesRegex(normals.GenerationError, "900s retry delay"):
                    normals._request_batch([self.city], max_attempts=2)
        request.assert_called_once()
        sleep.assert_not_called()

    def test_server_error_keeps_short_retry_backoff(self) -> None:
        error = HTTPError("https://example.invalid", 503, "unavailable", {}, None)
        with patch.object(normals, "urlopen", side_effect=[error, io.StringIO("{}")]):
            with patch.object(normals.time, "sleep") as sleep:
                normals._request_batch([self.city], max_attempts=2)
        sleep.assert_called_once_with(5)

    def test_output_file_bytes_match_metadata_checksum(self) -> None:
        rows, metadata = normals._aggregate_city(self.city, self._response(), self.dates)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "normals.csv"
            metadata_output = Path(temporary) / "normals.json"
            with patch.object(normals, "_load_cities", return_value=[self.city]):
                with patch.object(normals, "generate", return_value=(rows, [metadata])):
                    status = normals.main([
                        "--output", str(output), "--metadata-output", str(metadata_output)
                    ])
            self.assertEqual(status, 0)
            saved_metadata = json.loads(metadata_output.read_text(encoding="utf-8"))
            saved_bytes = output.read_bytes()
            self.assertNotIn(b"\r\n", saved_bytes)
            self.assertEqual(
                hashlib.sha256(saved_bytes).hexdigest(), saved_metadata["output"]["sha256"]
            )


if __name__ == "__main__":
    unittest.main()
