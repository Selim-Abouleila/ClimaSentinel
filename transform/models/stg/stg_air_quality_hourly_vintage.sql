{{ config(tags=['forecast_vintage']) }}

-- Preserves every air-quality forecast retrieval as a separate vintage.
--
-- Grain: one row per (ingestion_run_id, city_id, valid_ts_utc).
-- Separate ingestion runs are never collapsed, even when they forecast the
-- same valid timestamp.

WITH ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY ingestion_run_id, city_id, valid_ts_utc
            ORDER BY
                ingested_at_utc DESC,
                european_aqi DESC,
                pm2_5 DESC,
                pm10 DESC,
                no2 DESC,
                o3 DESC
        ) AS _row_num
    FROM {{ source('raw', 'air_quality_hourly') }}
)

SELECT
    ingestion_run_id,
    ingested_at_utc,
    DATE(ingested_at_utc) AS forecast_origin_date,
    city_id,
    valid_ts_utc,
    DATE(valid_ts_utc) AS valid_date,
    DATE_DIFF(
        DATE(valid_ts_utc),
        DATE(ingested_at_utc),
        DAY
    ) AS horizon_days,
    european_aqi,
    pm2_5,
    pm10,
    no2,
    o3
FROM ranked
WHERE _row_num = 1
