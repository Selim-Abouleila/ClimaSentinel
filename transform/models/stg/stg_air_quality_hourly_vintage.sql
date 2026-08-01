{{ config(tags=['forecast_vintage']) }}

-- Preserves every air-quality forecast retrieval as a separate vintage.
--
-- Grain: one row per (ingestion_run_id, city_id, valid_ts_utc).
-- Separate ingestion runs are never collapsed, even when they forecast the
-- same valid timestamp.

WITH ranked AS (
    SELECT
        raw_air_quality.*,
        forecast_city.forecast_origin_time_zone,
        ROW_NUMBER() OVER (
            PARTITION BY
                raw_air_quality.ingestion_run_id,
                raw_air_quality.city_id,
                raw_air_quality.valid_ts_utc
            ORDER BY
                raw_air_quality.ingested_at_utc DESC,
                raw_air_quality.european_aqi DESC,
                raw_air_quality.pm2_5 DESC,
                raw_air_quality.pm10 DESC,
                raw_air_quality.no2 DESC,
                raw_air_quality.o3 DESC
        ) AS _row_num
    FROM {{ source('raw', 'air_quality_hourly') }} AS raw_air_quality
    INNER JOIN {{ ref('forecast_city_allowlist') }} AS forecast_city
        ON raw_air_quality.city_id = forecast_city.city_id
)

SELECT
    ingestion_run_id,
    ingested_at_utc,
    forecast_origin_time_zone,
    DATE(ingested_at_utc, forecast_origin_time_zone) AS forecast_origin_date,
    city_id,
    valid_ts_utc,
    DATE(valid_ts_utc) AS valid_date,
    DATE_DIFF(
        DATE(valid_ts_utc),
        DATE(ingested_at_utc, forecast_origin_time_zone),
        DAY
    ) AS horizon_days,
    european_aqi,
    pm2_5,
    pm10,
    no2,
    o3
FROM ranked
WHERE _row_num = 1
