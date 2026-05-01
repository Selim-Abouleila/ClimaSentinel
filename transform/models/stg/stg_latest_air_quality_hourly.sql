-- stg_latest_air_quality_hourly.sql
-- Deduplicates raw.air_quality_hourly: keeps only the freshest air quality reading
-- for each (city_id, valid_ts_utc) pair based on ingestion timestamp.

WITH ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY city_id, valid_ts_utc
            ORDER BY ingested_at_utc DESC
        ) AS _row_num
    FROM {{ source('raw', 'air_quality_hourly') }}
)

SELECT
    city_id,
    valid_ts_utc,
    european_aqi,
    pm2_5,
    pm10,
    no2,
    o3,
    ingestion_run_id,
    ingested_at_utc
FROM ranked
WHERE _row_num = 1
