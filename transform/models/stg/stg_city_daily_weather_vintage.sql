{{ config(tags=['forecast_vintage']) }}

-- Aggregates weather inside one forecast vintage only.
--
-- Grain: one row per (ingestion_run_id, city_id, valid_date).
-- Null measurements are deliberately preserved rather than converted to zero.
-- Reading counts make incomplete provider responses observable downstream.

SELECT
    ingestion_run_id,
    ingested_at_utc,
    forecast_origin_time_zone,
    forecast_origin_date,
    city_id,
    valid_date,
    horizon_days,

    ROUND(AVG(temperature_2m), 2) AS temperature_2m_mean,
    ROUND(MAX(temperature_2m), 2) AS temperature_2m_max,
    ROUND(MIN(temperature_2m), 2) AS temperature_2m_min,
    ROUND(SUM(precipitation_mm), 2) AS precipitation_sum_mm,
    ROUND(MAX(wind_speed_10m), 2) AS wind_speed_10m_max,
    ROUND(MAX(wind_gusts_10m), 2) AS wind_gusts_10m_max,
    MAX(weather_code) AS weather_code_max,

    COUNT(*) AS hour_count,
    COUNT(DISTINCT valid_ts_utc) AS distinct_hour_count,
    COUNT(temperature_2m) AS temperature_reading_count,
    COUNT(precipitation_mm) AS precipitation_reading_count,
    COUNT(wind_speed_10m) AS wind_speed_reading_count,
    COUNT(wind_gusts_10m) AS wind_gusts_reading_count,
    COUNT(weather_code) AS weather_code_reading_count,
    COUNT(DISTINCT valid_ts_utc) = 24 AS has_24_hour_coverage,
    COUNTIF(
        temperature_2m IS NULL
        OR precipitation_mm IS NULL
        OR wind_speed_10m IS NULL
        OR wind_gusts_10m IS NULL
        OR weather_code IS NULL
    ) = 0 AS has_complete_weather_values

FROM {{ ref('stg_weather_forecast_hourly_vintage') }}
GROUP BY
    ingestion_run_id,
    ingested_at_utc,
    forecast_origin_time_zone,
    forecast_origin_date,
    city_id,
    valid_date,
    horizon_days
