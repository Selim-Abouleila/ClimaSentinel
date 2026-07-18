{{ config(tags=['forecast_vintage']) }}

-- Preserves every river-discharge forecast retrieval as a separate vintage.
-- Only river-enabled cities are expected to have rows in this model.
--
-- Grain: one row per (ingestion_run_id, city_id, valid_date).

WITH ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY ingestion_run_id, city_id, date
            ORDER BY ingested_at_utc DESC, river_discharge_m3s DESC
        ) AS _row_num
    FROM {{ source('raw', 'flood_daily') }}
)

SELECT
    ingestion_run_id,
    ingested_at_utc,
    DATE(ingested_at_utc) AS forecast_origin_date,
    city_id,
    date AS valid_date,
    DATE_DIFF(date, DATE(ingested_at_utc), DAY) AS horizon_days,
    river_discharge_m3s,
    river_discharge_m3s IS NOT NULL AS has_river_discharge_value
FROM ranked
WHERE _row_num = 1
