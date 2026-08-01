{{ config(tags=['forecast_vintage']) }}

-- Preserves every river-discharge forecast retrieval as a separate vintage.
-- Only river-enabled cities are expected to have rows in this model.
--
-- Grain: one row per (ingestion_run_id, city_id, valid_date).

WITH ranked AS (
    SELECT
        raw_flood.*,
        forecast_city.forecast_origin_time_zone,
        ROW_NUMBER() OVER (
            PARTITION BY
                raw_flood.ingestion_run_id,
                raw_flood.city_id,
                raw_flood.date
            ORDER BY
                raw_flood.ingested_at_utc DESC,
                raw_flood.river_discharge_m3s DESC
        ) AS _row_num
    FROM {{ source('raw', 'flood_daily') }} AS raw_flood
    INNER JOIN {{ ref('forecast_city_allowlist') }} AS forecast_city
        ON raw_flood.city_id = forecast_city.city_id
)

SELECT
    ingestion_run_id,
    ingested_at_utc,
    forecast_origin_time_zone,
    DATE(ingested_at_utc, forecast_origin_time_zone) AS forecast_origin_date,
    city_id,
    date AS valid_date,
    DATE_DIFF(
        date,
        DATE(ingested_at_utc, forecast_origin_time_zone),
        DAY
    ) AS horizon_days,
    river_discharge_m3s,
    river_discharge_m3s IS NOT NULL AS has_river_discharge_value
FROM ranked
WHERE _row_num = 1
