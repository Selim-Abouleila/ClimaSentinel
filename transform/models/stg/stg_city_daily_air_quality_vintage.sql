{{ config(tags=['forecast_vintage']) }}

-- Aggregates air-quality values inside one forecast vintage only.
--
-- Grain: one row per (ingestion_run_id, city_id, valid_date).
-- Missing AQ values remain null. In particular, missing data is not treated as
-- zero pollution; reading counts and completeness flags expose partial days.

SELECT
    ingestion_run_id,
    ingested_at_utc,
    forecast_origin_time_zone,
    forecast_origin_date,
    city_id,
    valid_date,
    horizon_days,

    ROUND(AVG(european_aqi), 2) AS european_aqi_mean,
    MAX(european_aqi) AS european_aqi_max,
    ROUND(AVG(pm2_5), 2) AS pm2_5_mean,
    ROUND(AVG(pm10), 2) AS pm10_mean,
    ROUND(AVG(no2), 2) AS no2_mean,
    ROUND(AVG(o3), 2) AS o3_mean,

    COUNT(*) AS hour_count,
    COUNT(DISTINCT valid_ts_utc) AS distinct_hour_count,
    COUNT(european_aqi) AS european_aqi_reading_count,
    COUNT(pm2_5) AS pm2_5_reading_count,
    COUNT(pm10) AS pm10_reading_count,
    COUNT(no2) AS no2_reading_count,
    COUNT(o3) AS o3_reading_count,
    COUNT(DISTINCT valid_ts_utc) = 24 AS has_24_hour_coverage,
    COUNTIF(
        european_aqi IS NULL
        OR pm2_5 IS NULL
        OR pm10 IS NULL
        OR no2 IS NULL
        OR o3 IS NULL
    ) = 0 AS has_complete_air_quality_values

FROM {{ ref('stg_air_quality_hourly_vintage') }}
GROUP BY
    ingestion_run_id,
    ingested_at_utc,
    forecast_origin_time_zone,
    forecast_origin_date,
    city_id,
    valid_date,
    horizon_days
