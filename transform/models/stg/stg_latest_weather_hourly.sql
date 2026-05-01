-- stg_latest_weather_hourly.sql
-- Deduplicates raw.weather_forecast_hourly: keeps only the freshest forecast
-- for each (city_id, valid_ts_utc) pair based on ingestion timestamp.
-- This eliminates overlapping 7-day forecast windows from successive daily runs.

WITH ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY city_id, valid_ts_utc
            ORDER BY ingested_at_utc DESC
        ) AS _row_num
    FROM {{ source('raw', 'weather_forecast_hourly') }}
)

SELECT
    city_id,
    valid_ts_utc,
    temperature_2m,
    precipitation_mm,
    wind_speed_10m,
    wind_gusts_10m,
    weather_code,
    ingestion_run_id,
    ingested_at_utc
FROM ranked
WHERE _row_num = 1
