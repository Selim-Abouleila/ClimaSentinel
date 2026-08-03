{{ config(
    materialized='view'
) }}

-- Exact-run daily river discharge for monitored river cities. Absence from the
-- selected run stays absent; no older forecast is borrowed.

WITH selected_run AS (
    SELECT *
    FROM {{ ref('stg_operational_run_v2') }}
),

ranked AS (
    SELECT
        raw_flood.*,
        ROW_NUMBER() OVER (
            PARTITION BY
                raw_flood.ingestion_run_id,
                raw_flood.city_id,
                raw_flood.date
            ORDER BY
                raw_flood.ingested_at_utc DESC,
                TO_JSON_STRING(STRUCT(
                    raw_flood.river_discharge_m3s AS river_discharge_m3s
                )) DESC
        ) AS _row_number
    FROM {{ source('raw', 'flood_daily') }} AS raw_flood
    INNER JOIN {{ ref('city_signal_monitoring') }} AS monitoring
        ON raw_flood.city_id = monitoring.city_id
    INNER JOIN selected_run
        ON CAST(raw_flood.ingestion_run_id AS STRING)
            = selected_run.operational_ingestion_run_id
    WHERE raw_flood.date IS NOT NULL
)

SELECT
    CAST(ingestion_run_id AS STRING) AS ingestion_run_id,
    ingested_at_utc AS flood_ingested_at_utc,
    city_id,
    date,
    river_discharge_m3s
FROM ranked
WHERE _row_number = 1
