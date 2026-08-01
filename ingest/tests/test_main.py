"""Failure-reporting contracts for the Cloud Run ingestion entrypoint."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

import main as ingest_main


def test_run_dbt_propagates_seed_failure() -> None:
    failure = subprocess.CalledProcessError(returncode=2, cmd=["dbt", "seed"])

    with patch.object(ingest_main.subprocess, "run", side_effect=failure):
        with pytest.raises(subprocess.CalledProcessError) as exc_info:
            ingest_main.run_dbt()

    assert exc_info.value is failure


def test_run_dbt_propagates_model_failure() -> None:
    failure = subprocess.CalledProcessError(returncode=3, cmd=["dbt", "run"])

    with patch.object(
        ingest_main.subprocess,
        "run",
        side_effect=[MagicMock(returncode=0), failure],
    ):
        with pytest.raises(subprocess.CalledProcessError) as exc_info:
            ingest_main.run_dbt()

    assert exc_info.value is failure


def test_partial_source_failure_refreshes_marts_then_exits_nonzero() -> None:
    city = {"city_id": "vienna_at", "river_enabled": "false"}

    def fake_fetch_and_insert(
        label,
        fetch_fn,
        insert_fn,
        current_city,
        client,
        run_id,
        started_at,
        errors,
    ) -> int:
        del fetch_fn, insert_fn, client, run_id, started_at
        assert current_city is city
        if label == "air_quality":
            errors.append("air_quality failed for vienna_at: upstream timeout")
            return 0
        return 1

    with (
        patch.object(ingest_main, "load_cities", return_value=[city]),
        patch.object(ingest_main.bigquery, "Client", return_value=MagicMock()),
        patch.object(
            ingest_main,
            "_fetch_and_insert",
            side_effect=fake_fetch_and_insert,
        ),
        patch.object(ingest_main, "run_dbt") as mock_run_dbt,
    ):
        with pytest.raises(SystemExit) as exc_info:
            ingest_main.run()

    assert exc_info.value.code == 1
    mock_run_dbt.assert_called_once_with()
