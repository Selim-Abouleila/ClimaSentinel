# 12. API and Swagger Reference

FastAPI generates the authoritative OpenAPI document at `/openapi.json` and the
interactive Swagger UI at `/docs`.

## Base information

- Local base URL: `http://127.0.0.1:8000`
- Content type: `application/json`
- Forecast horizons: integer `1`, `2` or `3`

## System endpoints

### `GET /`

Returns service metadata and the documentation route.

```json
{
  "service": "ClimaSentinel",
  "version": "1.0.0",
  "docs": "/docs"
}
```

### `GET /health`

Returns process health, environment and uptime for deployment checks.

```json
{
  "status": "healthy",
  "environment": "production",
  "uptime_seconds": 120.5
}
```

## Operational data endpoints

### `GET /data/current-scores`

Reads `mart_city_score_current`. `limit` defaults to `10`.

### `GET /data/history-scores`

Reads `mart_city_score_history`. Accepts optional `city_id` and a `limit` that
defaults to `50`.

### `GET /data/current-zones`

Reads `mart_city_zone_current`. `limit` defaults to `20`.

### `GET /data/city/{city_id}/scores`

Returns the five current operational factors from `mart_city_score_detail`.
These are operational score-mart outputs, not claims that all five factors have
realized-label model validation.

```json
{
  "city_id": "paris_fr",
  "current_tipping_score": 42.5,
  "current_primary_driver": "Heat",
  "heat_score": 60.0,
  "wind_score": 20.0,
  "rain_score": 10.0,
  "air_score": 50.0,
  "river_score": 5.0
}
```

## Rule-baseline forecast endpoint

### `GET /data/city/{city_id}/forecast`

Returns one genuine horizon from the point-in-time same-vintage rule policy.

- Path: `city_id`, for example `paris_fr`
- Query: `horizon_days`, default `3`, accepted values `1`, `2`, `3`
- Rule outputs: Heat, Rain, Wind, Air Quality and River from same-vintage
  forecasts
- Validation scope: limited ERA5 backtest for Heat; an ERA5 backtest with
  insufficient predictive skill for Rain; no observed-label validation yet for
  Wind, Air Quality and River

Example response where Heat is the primary driver and AQ is unavailable:

```json
{
  "city_id": "paris_fr",
  "horizon_days": 3,
  "prediction_date": "2026-07-18",
  "current_tipping_score": 25.0,
  "estimated_total_tipping_score": 61.2,
  "total_confidence_margin": null,
  "total_ci_lower": null,
  "total_ci_upper": null,
  "total_uncertainty_method": "none",
  "forecast_primary_driver": "Heat",
  "forecast_primary_driver_method": "forecast_rule",
  "sub_scores_forecast": {
    "heat_score": {
      "estimated_score": 61.2,
      "ci_lower": null,
      "ci_upper": null,
      "confidence_margin": null,
      "available": true,
      "method": "forecast_rule",
      "validation_status": "era5_backtested_limited",
      "uncertainty_method": "none",
      "provenance": "same-vintage weather forecast plus target-month city climatology",
      "method_reason": "Reviewed operational baseline; offline challenger promotion does not change serving without a separate integration decision",
      "unavailable_reason": null
    },
    "rain_score": {
      "estimated_score": 4.0,
      "ci_lower": null,
      "ci_upper": null,
      "confidence_margin": null,
      "available": true,
      "method": "forecast_rule",
      "validation_status": "era5_backtested_insufficient_skill",
      "uncertainty_method": "none",
      "provenance": "same-vintage daily precipitation forecast",
      "method_reason": "Reviewed operational baseline; its ERA5 backtest showed insufficient predictive skill, and challenger promotion does not change serving without a separate integration decision",
      "unavailable_reason": null
    },
    "wind_score": {
      "estimated_score": 17.5,
      "ci_lower": null,
      "ci_upper": null,
      "confidence_margin": null,
      "available": true,
      "method": "forecast_rule",
      "validation_status": "not_observation_validated",
      "uncertainty_method": "none",
      "provenance": "same-vintage wind-gust forecast",
      "method_reason": "Deterministic forecast rule; observed historical gust labels are not currently ingested",
      "unavailable_reason": null
    },
    "air_score": {
      "estimated_score": null,
      "ci_lower": null,
      "ci_upper": null,
      "confidence_margin": null,
      "available": false,
      "method": "forecast_rule",
      "validation_status": "not_observation_validated",
      "uncertainty_method": "none",
      "provenance": "same-vintage air-quality forecast",
      "method_reason": "Deterministic forecast rule; observed historical air-quality labels are not currently ingested",
      "unavailable_reason": "Same-vintage air-quality forecast is unavailable"
    },
    "river_score": {
      "estimated_score": 0.0,
      "ci_lower": null,
      "ci_upper": null,
      "confidence_margin": null,
      "available": true,
      "method": "forecast_rule",
      "validation_status": "not_observation_validated",
      "uncertainty_method": "none",
      "provenance": "same-vintage river-discharge forecast",
      "method_reason": "Deterministic forecast rule; observed historical river discharge labels are not currently ingested",
      "unavailable_reason": null
    }
  },
  "weather_trajectory": {
    "temp_max_plus_1d": 30.0,
    "temp_max_plus_2d": 28.5,
    "temp_max_plus_3d": 29.4,
    "precip_plus_3d": 2.0,
    "wind_plus_3d": 18.8
  },
  "prediction_source": "same_vintage_forecast_rules",
  "model_version": null,
  "forecast_method": "forecast_rules_baseline",
  "model_target_components": [],
  "rule_based_components": ["heat", "wind", "rain", "air", "river"],
  "feature_schema_version": "3",
  "feature_ingestion_run_id": "3b6f30d3-6ad2-45c4-a941-f5b606e1e88e",
  "feature_ingested_at_utc": "2026-07-18T05:30:00+00:00",
  "forecast_origin_time_zone": "Europe/Paris"
}
```

### Field semantics

| Field | Meaning |
|---|---|
| `method` | `forecast_rule` for every component in the current operational policy |
| `validation_status` | `era5_backtested_limited` for Heat; `era5_backtested_insufficient_skill` for Rain; `not_observation_validated` for Wind, Air Quality and River |
| `available` | Whether all inputs required for that component and horizon are present |
| `uncertainty_method` | `none`; the formulas do not claim model uncertainty |
| `provenance` | The exact same-vintage source inputs used by the component rule |
| `method_reason` | Why the operational policy uses that rule instead of claiming a learned output |
| `prediction_source` | `same_vintage_forecast_rules` for this operational policy |
| `model_version` | `null`; offline challenger registration is not serving provenance |
| `prediction_date` | City-local forecast origin date for the exact serving vintage |
| `feature_ingestion_run_id` | Exact same-vintage feature run used by the response |

`estimated_score: 0.0` means the component had sufficient source data and its
calculation genuinely evaluated to zero. `estimated_score: null` plus
`available: false` means the source contract was not satisfied. Clients must not
render those states as equivalent.

All component and top-level interval fields are null and
`total_uncertainty_method` is `none`. A deterministic formula is not a
statistical confidence interval.

### Error responses

| Status | Condition |
|---:|---|
| `404` | No current eligible point-in-time serving row exists for the city |
| `422` | `horizon_days` is outside `1..3` or another request value is invalid |
| `500` | BigQuery or unexpected application failure |
