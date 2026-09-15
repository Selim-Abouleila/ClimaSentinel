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
        "cold_in_global_score": False,
        "monitored_factor_count": 4,
        "available_factor_count": 3,
        "overall_coverage": 0.875,
        "heat_score": 43.9,
        "heat_status": "available",
        "heat_monitored": True,
        "heat_available": True,
        "heat_coverage": 1.0,
        "cold_score": 100.0,
        "cold_status": "available",
        "cold_monitored": True,
        "cold_available": True,
        "cold_coverage": 1.0,
        "temperature_2m_min": -20.0,
        "normal_temperature_2m_min": 0.0,
        "cold_anomaly_c": 20.0,
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
            "cold_in_global_score": False,
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
                "cold_in_global_score": False,
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
        "cold_in_global_score",
        "cold_score",
        "cold_status",
        "cold_monitored",
        "cold_available",
        "cold_coverage",
        "temperature_2m_min",
        "normal_temperature_2m_min",
        "cold_anomaly_c",
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
            "cold_in_global_score": False,
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
            "cold_in_global_score": False,
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
        "cold_in_global_score",
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
            "cold_in_global_score": False,
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


def _operational_payload(row: dict[str, object], kind: str) -> dict[str, object]:
    if kind == "current":
        return {
            **{key: row[key] for key in CurrentCityScoreResponse.model_fields if key != "rank"},
            "rank": 1,
        }
    if kind == "history":
        result = deepcopy(row)
        result.update(
            date=result.pop("score_date"),
            global_tipping_score=result.pop("current_tipping_score"),
            primary_driver=result.pop("current_primary_driver"),
            global_score_available=result.pop("current_score_available"),
            temperature_2m_max=33.4,
            precipitation_sum_mm=0.9,
            wind_gusts_10m_max=76.7,
            european_aqi_max=None,
            river_discharge_m3s=None,
        )
        return result
    return deepcopy(row)


def _score_endpoint(kind: str) -> str:
    return {
        "current": "/data/current-scores",
        "detail": "/data/city/stockholm_se/scores",
        "history": "/data/history-scores?city_id=stockholm_se&limit=1",
    }[kind]


def _score_schema(kind: str):
    return {
        "current": CurrentCityScoreResponse,
        "detail": CityScoreDetailResponse,
        "history": CityScoreHistoryResponse,
    }[kind]


def _enabled_cold_row() -> dict[str, object]:
    row = _city_score_row()
    row.update(
        cold_in_global_score=True,
        current_tipping_score=100.0,
        current_primary_driver="Cold",
        monitored_factor_count=5,
        available_factor_count=4,
        overall_coverage=0.9,
    )
    return row


@pytest.mark.parametrize("kind", ["current", "detail", "history"])
@pytest.mark.parametrize("enabled", [False, True])
def test_endpoints_follow_explicit_warehouse_aggregation_mode(kind: str, enabled: bool) -> None:
    row = _enabled_cold_row() if enabled else _city_score_row()
    payload = _operational_payload(row, kind)
    bq_client = MagicMock()
    bq_client.query.return_value.result.return_value = [payload]
    with patch("app.main.get_bq_client", return_value=bq_client):
        response = client.get(_score_endpoint(kind))
    assert response.status_code == 200
    body = response.json() if kind == "detail" else response.json()[0]
    assert body["cold_in_global_score"] is enabled
    score_key = "global_tipping_score" if kind == "history" else "current_tipping_score"
    driver_key = "primary_driver" if kind == "history" else "current_primary_driver"
    assert body[score_key] == (100.0 if enabled else 91.8)
    assert body[driver_key] == ("Cold" if enabled else "Wind")
    assert body["monitored_factor_count"] == (5 if enabled else 4)
    if kind != "current":
        assert body["cold_score"] == 100.0
        assert body["cold_available"] is True
        assert body["temperature_2m_min"] == -20.0
        assert body["normal_temperature_2m_min"] == 0.0
        assert body["cold_anomaly_c"] == 20.0


@pytest.mark.parametrize("kind", ["current", "detail", "history"])
@pytest.mark.parametrize("invalid", ["missing", None, "false", "true", 0, 1])
def test_aggregation_mode_is_required_and_strict(kind: str, invalid: object) -> None:
    row = _operational_payload(_city_score_row(), kind)
    if invalid == "missing":
        del row["cold_in_global_score"]
    else:
        row["cold_in_global_score"] = invalid
    with pytest.raises(ValidationError, match="cold_in_global_score"):
        _score_schema(kind).model_validate(row)


@pytest.mark.parametrize("kind", ["current", "detail", "history"])
def test_endpoint_rejects_missing_warehouse_mode(kind: str) -> None:
    row = _operational_payload(_city_score_row(), kind)
    del row["cold_in_global_score"]
    bq_client = MagicMock()
    bq_client.query.return_value.result.return_value = [row]
    with patch("app.main.get_bq_client", return_value=bq_client):
        response = TestClient(app, raise_server_exceptions=False).get(_score_endpoint(kind))
    assert response.status_code == 500


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize(
    ("state", "coverage", "expected_count", "expected_coverage"),
    [
        ("unavailable", 0.0, 5, 0.7),
        ("unavailable", 0.958, 5, 0.892),
        ("not_monitored", None, 4, 0.875),
    ],
)
def test_cold_missingness_and_partial_coverage_in_each_mode(
    enabled: bool, state: str, coverage: float | None,
    expected_count: int, expected_coverage: float,
) -> None:
    row = _city_score_row()
    row.update(
        cold_in_global_score=enabled,
        cold_score=None,
        cold_status=state,
        cold_monitored=state != "not_monitored",
        cold_available=False,
        cold_coverage=coverage,
        cold_anomaly_c=None,
        monitored_factor_count=expected_count if enabled else 4,
        overall_coverage=expected_coverage if enabled else 0.875,
    )
    response = CityScoreDetailResponse.model_validate(row)
    assert response.cold_score is None
    assert response.current_primary_driver == "Wind"
    assert response.available_factor_count == 3
    assert response.cold_coverage == coverage


@pytest.mark.parametrize("score", [None, 0.0, 75.0])
@pytest.mark.parametrize("kind", ["current", "detail", "history"])
def test_enabled_cold_as_the_only_available_factor(score: float | None, kind: str) -> None:
    row = _city_score_row()
    for factor in ("heat", "cold", "wind", "rain", "air", "river"):
        row.update({
            f"{factor}_score": None,
            f"{factor}_status": "unavailable",
            f"{factor}_monitored": True,
            f"{factor}_available": False,
            f"{factor}_coverage": 0.0,
        })
    available = score is not None
    row.update(
        cold_in_global_score=True,
        cold_score=score,
        cold_status="available" if available else "unavailable",
        cold_available=available,
        cold_coverage=1.0 if available else 0.0,
        current_tipping_score=score,
        current_primary_driver="Unavailable" if not available else "Stable" if score == 0 else "Cold",
        current_score_available=available,
        monitored_factor_count=6,
        available_factor_count=int(available),
        overall_coverage=0.167 if available else 0.0,
    )
    bq_client = MagicMock()
    bq_client.query.return_value.result.return_value = [_operational_payload(row, kind)]
    with patch("app.main.get_bq_client", return_value=bq_client):
        response = client.get(_score_endpoint(kind))
    assert response.status_code == 200
    body = response.json() if kind == "detail" else response.json()[0]
    assert body["available_factor_count"] == int(available)
    assert body["global_tipping_score" if kind == "history" else "current_tipping_score"] == score


@pytest.mark.parametrize(
    "updates",
    [
        {"cold_in_global_score": False},
        {"monitored_factor_count": 4},
        {"available_factor_count": 3},
        {"overall_coverage": 0.875},
        {"current_tipping_score": 91.8},
        {"current_primary_driver": "Wind"},
        {"current_primary_driver": "Stable"},
    ],
)
@pytest.mark.parametrize("kind", ["detail", "history"])
def test_six_factor_contract_rejects_mismatched_aggregates(updates: dict, kind: str) -> None:
    row = _enabled_cold_row()
    row.update(updates)
    with pytest.raises(ValidationError):
        _score_schema(kind).model_validate(_operational_payload(row, kind))


@pytest.mark.parametrize("updates", [{"monitored_factor_count": 6}, {"current_primary_driver": "Cold"}])
def test_overview_rejects_six_factor_claims_in_five_factor_mode(updates: dict) -> None:
    row = _operational_payload(_city_score_row(), "current")
    row.update(updates)
    with pytest.raises(ValidationError):
        CurrentCityScoreResponse.model_validate(row)


@pytest.mark.parametrize("updates", [
    {"cold_monitored": False}, {"cold_available": False}, {"cold_coverage": 0.5},
    {"cold_score": None}, {"cold_status": "not_monitored"},
])
def test_cold_metadata_is_validated_even_when_excluded_from_aggregate(updates: dict) -> None:
    row = _city_score_row()
    row.update(updates)
    with pytest.raises(ValidationError):
        CityScoreDetailResponse.model_validate(row)


@pytest.mark.parametrize("driver", ["Heat", "Wind", "Cold"])
def test_published_score_ties_do_not_override_the_warehouse_driver(driver: str) -> None:
    row = _enabled_cold_row()
    row.update(heat_score=91.8, cold_score=91.8, current_tipping_score=91.8, current_primary_driver=driver)
    assert CityScoreDetailResponse.model_validate(row).current_primary_driver == driver


@pytest.mark.parametrize("kind", ["detail", "history"])
@pytest.mark.parametrize("invalid", [None, float("nan"), float("inf"), float("-inf")])
def test_cold_context_serializes_missing_and_nonfinite_values_as_null(kind: str, invalid: float | None) -> None:
    row = _city_score_row()
    row.update(temperature_2m_min=invalid, normal_temperature_2m_min=invalid, cold_anomaly_c=invalid,
               cold_score=None, cold_available=False, cold_status="unavailable", cold_coverage=0.0)
    bq_client = MagicMock()
    bq_client.query.return_value.result.return_value = [_operational_payload(row, kind)]
    with patch("app.main.get_bq_client", return_value=bq_client):
        response = client.get(_score_endpoint(kind))
    assert response.status_code == 200
    body = response.json() if kind == "detail" else response.json()[0]
    assert body["temperature_2m_min"] is None
    assert body["normal_temperature_2m_min"] is None
    assert body["cold_anomaly_c"] is None


def test_openapi_requires_mode_and_nullable_cold_contract_fields() -> None:
    schemas = client.get("/openapi.json").json()["components"]["schemas"]
    for name in ("CurrentCityScoreResponse", "CityScoreDetailResponse", "CityScoreHistoryResponse"):
        assert "cold_in_global_score" in schemas[name]["required"]
        assert schemas[name]["properties"]["cold_in_global_score"]["type"] == "boolean"
    for name in ("CityScoreDetailResponse", "CityScoreHistoryResponse"):
        for field in ("cold_score", "cold_status", "cold_monitored", "cold_available", "cold_coverage",
                      "temperature_2m_min", "normal_temperature_2m_min", "cold_anomaly_c"):
            assert field in schemas[name]["required"]
        for field in ("cold_score", "cold_coverage", "temperature_2m_min", "normal_temperature_2m_min", "cold_anomaly_c"):
            assert {"type": "null"} in schemas[name]["properties"][field]["anyOf"]
