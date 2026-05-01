-- stg_city_daily_weather.sql
-- Aggregates deduplicated hourly weather into one row per (city_id, date).
-- Computes daily summary statistics: mean/max/min temperature, total precipitation,
-- max wind speed and gusts, and the most severe weather code of the day.

SELECT
    city_id,
    DATE(valid_ts_utc) AS date,

    -- Temperature
    ROUND(AVG(temperature_2m), 2)                AS temperature_2m_mean,
    ROUND(MAX(temperature_2m), 2)                AS temperature_2m_max,
    ROUND(MIN(temperature_2m), 2)                AS temperature_2m_min,

    -- Precipitation
    ROUND(SUM(COALESCE(precipitation_mm, 0)), 2) AS precipitation_sum_mm,

    -- Wind
    ROUND(MAX(COALESCE(wind_speed_10m, 0)), 2)   AS wind_speed_10m_max,
    ROUND(MAX(COALESCE(wind_gusts_10m, 0)), 2)   AS wind_gusts_10m_max,

    -- Weather code (highest = most severe in the day)
    MAX(weather_code)                             AS weather_code_max,

    -- Quality: number of hourly readings (expect 24 for a complete day)
    COUNT(*)                                      AS hour_count

FROM {{ ref('stg_latest_weather_hourly') }}
GROUP BY city_id, DATE(valid_ts_utc)
