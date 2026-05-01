-- stg_city_daily_air_quality.sql
-- Aggregates deduplicated hourly air quality into one row per (city_id, date).
-- Computes daily summary statistics: mean and max AQI, mean PM2.5, PM10, NO₂, O₃.

SELECT
    city_id,
    DATE(valid_ts_utc) AS date,

    -- European AQI
    ROUND(AVG(COALESCE(european_aqi, 0)), 2) AS european_aqi_mean,
    MAX(european_aqi)                         AS european_aqi_max,

    -- Particulate matter
    ROUND(AVG(COALESCE(pm2_5, 0)), 2)        AS pm2_5_mean,
    ROUND(AVG(COALESCE(pm10, 0)), 2)         AS pm10_mean,

    -- Gases
    ROUND(AVG(COALESCE(no2, 0)), 2)          AS no2_mean,
    ROUND(AVG(COALESCE(o3, 0)), 2)           AS o3_mean,

    -- Quality: number of hourly readings (expect 24 for a complete day)
    COUNT(*)                                  AS hour_count

FROM {{ ref('stg_latest_air_quality_hourly') }}
GROUP BY city_id, DATE(valid_ts_utc)
