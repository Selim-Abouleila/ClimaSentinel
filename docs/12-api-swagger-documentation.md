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

## Hybrid forecast endpoint

### `GET /data/city/{city_id}/forecast`

Returns one genuine horizon from the schema-v3 hybrid forecaster.

- Path: `city_id`, for example `paris_fr`
- Query: `horizon_days`, default `3`, accepted values `1`, `2`, `3`
- Learned outputs: Heat and Rain from `ClimaSentinel_HeatRainForecaster`
- Rule outputs: Wind, Air Quality and River from same-vintage forecasts

Example response where Heat is the primary driver and AQ is unavailable:

```json
{
  "city_id": "paris_fr",
  "horizon_days": 3,
  "prediction_date": "2026-07-18",
  "current_tipping_score": 25.0,
  "estimated_total_tipping_score": 61.2,
  "total_confidence_margin": 5.4,
  "total_ci_lower": 55.8,
  "total_ci_upper": 66.6,
  "total_uncertainty_method": "tree_spread_not_calibrated",
  "forecast_primary_driver": "Heat",
  "forecast_primary_driver_method": "learned_model",
  "sub_scores_forecast": {
    "heat_score": {
      "estimated_score": 61.2,
      "ci_lower": 55.8,
      "ci_upper": 66.6,
      "confidence_margin": 5.4,
      "available": true,
      "method": "learned_model",
      "validation_status": "era5_realized_validated",
      "uncertainty_method": "tree_spread_not_calibrated",
      "unavailable_reason": null
    },
    "rain_score": {
      "estimated_score": 4.0,
      "ci_lower": 2.1,
      "ci_upper": 5.9,
      "confidence_margin": 1.9,
      "available": true,
      "method": "learned_model",
      "validation_status": "era5_realized_validated",
      "uncertainty_method": "tree_spread_not_calibrated",
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
  "prediction_source": "mlflow_registry",
  "model_version": "42",
  "forecast_method": "hybrid_ml_and_forecast_rules",
  "model_target_components": ["heat", "rain"],
  "rule_based_components": ["wind", "air", "river"],
  "feature_schema_version": "3",
  "feature_ingestion_run_id": "3b6f30d3-6ad2-45c4-a941-f5b606e1e88e",
  "feature_ingested_at_utc": "2026-07-18T05:30:00+00:00",
  "forecast_origin_time_zone": "Europe/Paris"
}
```

### Field semantics

| Field | Meaning |
|---|---|
| `method` | `learned_model`, `forecast_rule`, or an explicitly identified development fallback |
| `validation_status` | Whether the component was validated against realized ERA5 outcomes |
| `available` | Whether all inputs required for that component and horizon are present |
| `uncertainty_method` | `tree_spread_not_calibrated` for learned outputs, otherwise `none` |
| `prediction_source` | Provenance of the Heat/Rain estimator, retained for client compatibility |
| `model_version` | Concrete registry version actually loaded, even when selected through an alias |
| `prediction_date` | City-local forecast origin date for the exact serving vintage |
| `feature_ingestion_run_id` | Exact same-vintage feature run used by the response |

`estimated_score: 0.0` means the component had sufficient source data and its
calculation genuinely evaluated to zero. `estimated_score: null` plus
`available: false` means the source contract was not satisfied. Clients must not
render those states as equivalent.

The tree-spread fields are not calibrated 95% confidence intervals. When the
primary driver is a forecast rule, all top-level interval fields are null and
`total_uncertainty_method` is `none`.

### Error responses

| Status | Condition |
|---:|---|
| `404` | No current eligible point-in-time serving row exists for the city |
| `422` | `horizon_days` is outside `1..3` or another request value is invalid |
| `500` | BigQuery or unexpected application failure |
| `503` | Registered model selection, loading, schema validation or inference failed in a protected environment |
