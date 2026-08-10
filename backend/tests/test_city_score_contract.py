"""Contract tests for current city factor scores and signal availability."""

from copy import deepcopy
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.schemas import (
    CityScoreDetailResponse,
    CityScoreHistoryResponse,
    CurrentCityScoreResponse,
)


client = TestClient(app)


def _city_score_row() -> dict[str, object]:
    """A complete row with both missing-data states represented explicitly."""
    return {
        "operational_ingestion_run_id": "run-2026-08-03",
        "operational_ingested_at_utc": "2026-08-03T06:00:00+00:00",
        "city_id": "stockholm_se",
        "score_date": date(2026, 8, 3),
        "current_tipping_score": 91.8,
        "current_primary_driver": "Wind",
        "current_score_available": True,
        "monitored_factor_count": 4,
        "available_factor_count": 3,
        "overall_coverage": 0.875,
        "heat_score": 43.9,
        "heat_status": "available",
        "heat_monitored": True,
        "heat_available": True,
        "heat_coverage": 1.0,
        "wind_score": 91.8,
        "wind_status": "available",
        "wind_monitored": True,
        "wind_available": True,
        "wind_coverage": 1.0,
        "rain_score": 15.4,
        "rain_status": "available",
        "rain_monitored": True,
        "rain_available": True,
        "rain_coverage": 1.0,
        "air_score": None,
        "air_status": "unavailable",
        "air_monitored": True,
        "air_available": False,
        "air_coverage": 0.5,
        "river_score": None,
        "river_status": "not_monitored",
        "river_monitored": False,
        "river_available": False,
        "river_coverage": None,
    }


def test_schema_preserves_unavailable_scores_as_null() -> None:
    response = CityScoreDetailResponse.model_validate(_city_score_row())

    payload = response.model_dump(mode="json")

    assert payload["air_score"] is None
    assert payload["air_status"] == "unavailable"
    assert payload["air_monitored"] is True
    assert payload["air_available"] is False
    assert payload["air_coverage"] == 0.5
    assert payload["river_score"] is None
    assert payload["river_status"] == "not_monitored"
    assert payload["river_monitored"] is False
    assert payload["river_available"] is False
    assert payload["river_coverage"] is None


def test_available_zero_is_distinct_from_missing() -> None:
    row = _city_score_row()
    row.update(
        {
            "air_score": 0.0,
            "air_status": "available",
            "air_available": True,
            "air_coverage": 1.0,
            "available_factor_count": 4,
            "overall_coverage": 1.0,
        }
    )

    response = CityScoreDetailResponse.model_validate(row)

    assert response.air_score == 0.0
    assert response.air_status == "available"
    assert response.air_available is True


def test_overall_score_can_be_unavailable_without_becoming_zero() -> None:
    response = CurrentCityScoreResponse.model_validate(
        {
            "operational_ingestion_run_id": "run-2026-08-03",
            "operational_ingested_at_utc": "2026-08-03T06:00:00+00:00",
            "city_id": "stockholm_se",
            "current_tipping_score": None,
            "current_primary_driver": "Unavailable",
            "current_score_available": False,
            "monitored_factor_count": 4,
            "available_factor_count": 0,
            "overall_coverage": 0.0,
            "rank": 20,
        }
    )

    assert response.current_tipping_score is None
    assert response.current_primary_driver == "Unavailable"
    assert response.current_score_available is False


def test_overview_schema_rejects_a_null_score_marked_available() -> None:
    with pytest.raises(ValidationError, match="current_score_available"):
        CurrentCityScoreResponse.model_validate(
            {
                "operational_ingestion_run_id": "run-2026-08-03",
                "operational_ingested_at_utc": "2026-08-03T06:00:00+00:00",
                "city_id": "stockholm_se",
                "current_tipping_score": None,
                "current_primary_driver": "Unavailable",
                "current_score_available": True,
                "monitored_factor_count": 4,
                "available_factor_count": 0,
                "overall_coverage": 0.0,
                "rank": 20,
            }
        )


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        (
            {"river_score": 0.0},
            "not_monitored",
        ),
        (
            {"air_score": 0.0},
            "unavailable",
        ),
        (
            {"air_status": "available", "air_available": True},
            "non-null score",
        ),
        (
            {"wind_coverage": None},
            "non-null coverage",
        ),
        (
            {"wind_coverage": 0.5},
            "coverage=1.0",
        ),
        (
            {"air_coverage": None},
            "non-null coverage",
        ),
        (
            {"air_coverage": 1.0},
            "coverage below 1.0",
        ),
        (
            {"river_status": "invalid"},
            "Input should be",
        ),
        (
            {"air_coverage": 1.1},
            "less than or equal to 1",
        ),
    ],
)
def test_schema_rejects_contradictory_or_invalid_metadata(
    updates: dict[str, object],
    message: str,
) -> None:
    row = deepcopy(_city_score_row())
    row.update(updates)

    with pytest.raises(ValidationError, match=message):
        CityScoreDetailResponse.model_validate(row)


def test_city_scores_endpoint_serializes_nulls_and_metadata() -> None:
    query_job = MagicMock()
    query_job.result.return_value = [_city_score_row()]
    bq_client = MagicMock()
    bq_client.query.return_value = query_job

    with patch("app.main.get_bq_client", return_value=bq_client):
        response = client.get("/data/city/stockholm_se/scores")

    assert response.status_code == 200
    payload = response.json()
    assert payload["air_score"] is None
    assert payload["air_status"] == "unavailable"
    assert payload["river_score"] is None
    assert payload["river_status"] == "not_monitored"
    assert payload["wind_score"] == 91.8
    assert payload["wind_status"] == "available"
    assert payload["current_score_available"] is True
    assert payload["available_factor_count"] == 3

    query = bq_client.query.call_args.args[0]
    assert "mart_city_score_detail_v2" in query
    for field in (
        "air_status",
        "air_monitored",
        "air_available",
        "air_coverage",
        "river_status",
        "river_monitored",
        "river_available",
        "river_coverage",
        "current_score_available",
        "available_factor_count",
        "monitored_factor_count",
        "overall_coverage",
    ):
        assert field in query

    job_config = bq_client.query.call_args.kwargs["job_config"]
    assert job_config.query_parameters[0].name == "city_id"
    assert job_config.query_parameters[0].value == "stockholm_se"


def test_city_score_openapi_contract_marks_scores_nullable() -> None:
    schema = client.get("/openapi.json").json()
    detail_schema = schema["components"]["schemas"]["CityScoreDetailResponse"]

    assert {"type": "null"} in detail_schema["properties"]["river_score"]["anyOf"]
    assert detail_schema["properties"]["river_status"]["enum"] == [
        "available",
        "not_monitored",
        "unavailable",
    ]
    assert detail_schema["properties"]["river_coverage"]["anyOf"][0]["maximum"] == 1.0


def test_current_scores_endpoint_preserves_an_unavailable_overall_score() -> None:
    query_job = MagicMock()
    query_job.result.return_value = [
        {
            "operational_ingestion_run_id": "run-2026-08-03",
            "operational_ingested_at_utc": "2026-08-03T06:00:00+00:00",
            "city_id": "stockholm_se",
            "current_tipping_score": None,
            "current_primary_driver": "Unavailable",
            "current_score_available": False,
            "monitored_factor_count": 4,
            "available_factor_count": 0,
            "overall_coverage": 0.0,
            "rank": 20,
        }
    ]
    bq_client = MagicMock()
    bq_client.query.return_value = query_job

    with patch("app.main.get_bq_client", return_value=bq_client):
        response = client.get("/data/current-scores")

    assert response.status_code == 200
    assert response.json() == [
        {
            "operational_ingestion_run_id": "run-2026-08-03",
            "operational_ingested_at_utc": "2026-08-03T06:00:00Z",
            "city_id": "stockholm_se",
            "current_tipping_score": None,
            "current_primary_driver": "Unavailable",
            "current_score_available": False,
            "monitored_factor_count": 4,
            "available_factor_count": 0,
            "overall_coverage": 0.0,
            "rank": 20,
        }
    ]
    query = bq_client.query.call_args.args[0]
    assert "mart_city_score_current_v2" in query
    assert "ORDER BY current_score_available DESC, rank ASC, city_id ASC" in query
    for field in (
        "current_score_available",
        "monitored_factor_count",
        "available_factor_count",
        "overall_coverage",
    ):
        assert field in query


def test_history_contract_preserves_factor_nulls_and_metadata() -> None:
    row = _city_score_row()
    history_row = {
        key: value
        for key, value in row.items()
        if key not in {
            "score_date",
            "current_tipping_score",
            "current_primary_driver",
            "current_score_available",
        }
    }
    history_row.update(
        {
            "date": date(2026, 8, 3),
            "temperature_2m_max": 33.4,
            "precipitation_sum_mm": 0.9,
            "wind_gusts_10m_max": 76.7,
            "european_aqi_max": None,
            "river_discharge_m3s": None,
            "monitored_factor_count": 4,
            "available_factor_count": 3,
            "overall_coverage": 0.875,
            "global_score_available": True,
            "global_tipping_score": 91.8,
            "primary_driver": "Wind",
        }
    )

    contract = CityScoreHistoryResponse.model_validate(history_row)

    assert contract.air_score is None
    assert contract.air_status == "unavailable"
    assert contract.river_score is None
    assert contract.river_status == "not_monitored"

    query_job = MagicMock()
    query_job.result.return_value = [history_row]
    bq_client = MagicMock()
    bq_client.query.return_value = query_job
    with patch("app.main.get_bq_client", return_value=bq_client):
        response = client.get("/data/history-scores?city_id=stockholm_se&limit=1")

    assert response.status_code == 200
    payload = response.json()[0]
    assert payload["air_score"] is None
    assert payload["river_score"] is None
    assert payload["global_tipping_score"] == 91.8
    history_query = bq_client.query.call_args.args[0]
    assert "mart_city_score_history_v2" in history_query
    assert "ORDER BY date DESC" in history_query


def test_detail_schema_rejects_counts_that_disagree_with_factor_flags() -> None:
    row = _city_score_row()
    row["available_factor_count"] = 2

    with pytest.raises(ValidationError, match="availability flags"):
        CityScoreDetailResponse.model_validate(row)


def test_detail_schema_rejects_aggregate_not_equal_to_available_maximum() -> None:
    row = _city_score_row()
    row["current_tipping_score"] = 43.9

    with pytest.raises(ValidationError, match="maximum available factor"):
        CityScoreDetailResponse.model_validate(row)


def test_detail_all_unavailable_remains_null() -> None:
    row = _city_score_row()
    for factor in ("heat", "wind", "rain", "air", "river"):
        row[f"{factor}_score"] = None
        row[f"{factor}_status"] = "unavailable"
        row[f"{factor}_monitored"] = True
        row[f"{factor}_available"] = False
        row[f"{factor}_coverage"] = 0.0
    row.update(
        {
            "current_tipping_score": None,
            "current_primary_driver": "Unavailable",
            "current_score_available": False,
            "monitored_factor_count": 5,
            "available_factor_count": 0,
            "overall_coverage": 0.0,
        }
    )

    response = CityScoreDetailResponse.model_validate(row)

    assert response.current_tipping_score is None
    assert response.current_score_available is False
    assert response.available_factor_count == 0


def test_measured_zero_survives_detail_endpoint_serialization() -> None:
    row = _city_score_row()
    row["heat_score"] = 0.0
    query_job = MagicMock()
    query_job.result.return_value = [row]
    bq_client = MagicMock()
    bq_client.query.return_value = query_job

    with patch("app.main.get_bq_client", return_value=bq_client):
        response = client.get("/data/city/stockholm_se/scores")

    assert response.status_code == 200
    assert response.json()["heat_score"] == 0.0
