-- stg_latest_flood_daily.sql
-- Deduplicates raw.flood_daily: keeps only the freshest river discharge reading
-- for each (city_id, date) pair based on ingestion timestamp.
-- Only river-enabled cities (Paris, Amsterdam, Warsaw) have data in this table.

WITH ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY city_id, date
            ORDER BY ingested_at_utc DESC
        ) AS _row_num
    FROM {{ source('raw', 'flood_daily') }}
)

SELECT
    city_id,
    date,
    river_discharge_m3s,
    ingestion_run_id,
    ingested_at_utc
FROM ranked
WHERE _row_num = 1
