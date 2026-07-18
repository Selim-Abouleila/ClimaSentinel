{{ config(tags=['forecast_vintage']) }}

-- Hard point-in-time invariants shared by every vintage model.

WITH vintage_rows AS (
    SELECT
        'stg_weather_forecast_hourly_vintage' AS model_name,
        ingestion_run_id,
        city_id,
        ingested_at_utc,
        forecast_origin_date,
        valid_date,
        horizon_days
    FROM {{ ref('stg_weather_forecast_hourly_vintage') }}

    UNION ALL

    SELECT
        'stg_city_daily_weather_vintage',
        ingestion_run_id,
        city_id,
        ingested_at_utc,
        forecast_origin_date,
        valid_date,
        horizon_days
    FROM {{ ref('stg_city_daily_weather_vintage') }}

    UNION ALL

    SELECT
        'stg_air_quality_hourly_vintage',
        ingestion_run_id,
        city_id,
        ingested_at_utc,
        forecast_origin_date,
        valid_date,
        horizon_days
    FROM {{ ref('stg_air_quality_hourly_vintage') }}

    UNION ALL

    SELECT
        'stg_city_daily_air_quality_vintage',
        ingestion_run_id,
        city_id,
        ingested_at_utc,
        forecast_origin_date,
        valid_date,
        horizon_days
    FROM {{ ref('stg_city_daily_air_quality_vintage') }}

    UNION ALL

    SELECT
        'stg_flood_daily_vintage',
        ingestion_run_id,
        city_id,
        ingested_at_utc,
        forecast_origin_date,
        valid_date,
        horizon_days
    FROM {{ ref('stg_flood_daily_vintage') }}

    UNION ALL

    SELECT
        'stg_city_signal_vintage',
        ingestion_run_id,
        city_id,
        ingested_at_utc,
        forecast_origin_date,
        valid_date,
        horizon_days
    FROM {{ ref('stg_city_signal_vintage') }}
)

SELECT
    model_name,
    ingestion_run_id,
    city_id,
    ingested_at_utc,
    forecast_origin_date,
    valid_date,
    horizon_days
FROM vintage_rows
WHERE ingestion_run_id IS NULL
   OR city_id IS NULL
   OR ingested_at_utc IS NULL
   OR forecast_origin_date IS NULL
   OR valid_date IS NULL
   OR horizon_days IS NULL
   OR forecast_origin_date != DATE(ingested_at_utc)
   OR horizon_days != DATE_DIFF(valid_date, forecast_origin_date, DAY)
