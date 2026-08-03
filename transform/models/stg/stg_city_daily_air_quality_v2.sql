{{ config(
    materialized='view'
) }}

-- Exact-run daily AQ. Aggregates remain nullable and expose populated-value
-- counts so a partial payload cannot be scored as a complete day.

WITH selected_run AS (
    SELECT *
    FROM {{ ref('stg_operational_run_v2') }}
),

ranked AS (
    SELECT
        raw_air_quality.*,
        ROW_NUMBER() OVER (
            PARTITION BY
                raw_air_quality.ingestion_run_id,
                raw_air_quality.city_id,
                raw_air_quality.valid_ts_utc
            ORDER BY
                raw_air_quality.ingested_at_utc DESC,
                TO_JSON_STRING(STRUCT(
                    raw_air_quality.european_aqi AS european_aqi,
                    raw_air_quality.pm2_5 AS pm2_5,
                    raw_air_quality.pm10 AS pm10,
                    raw_air_quality.no2 AS no2,
                    raw_air_quality.o3 AS o3
                )) DESC
        ) AS _row_number
    FROM {{ source('raw', 'air_quality_hourly') }} AS raw_air_quality
    INNER JOIN {{ ref('city_signal_monitoring') }} AS monitoring
        ON raw_air_quality.city_id = monitoring.city_id
    INNER JOIN selected_run
        ON CAST(raw_air_quality.ingestion_run_id AS STRING)
            = selected_run.operational_ingestion_run_id
    WHERE raw_air_quality.valid_ts_utc IS NOT NULL
),

deduplicated AS (
    SELECT * EXCEPT (_row_number)
    FROM ranked
    WHERE _row_number = 1
)

SELECT
    CAST(ingestion_run_id AS STRING) AS ingestion_run_id,
    MAX(ingested_at_utc) AS air_quality_ingested_at_utc,
    city_id,
    DATE(valid_ts_utc) AS date,
    ROUND(AVG(european_aqi), 2) AS european_aqi_mean,
    MAX(european_aqi) AS european_aqi_max,
    ROUND(AVG(pm2_5), 2) AS pm2_5_mean,
    ROUND(AVG(pm10), 2) AS pm10_mean,
    ROUND(AVG(no2), 2) AS no2_mean,
    ROUND(AVG(o3), 2) AS o3_mean,
    COUNT(*) AS air_quality_hour_count,
    COUNTIF(european_aqi IS NOT NULL) AS european_aqi_value_count
FROM deduplicated
GROUP BY ingestion_run_id, city_id, DATE(valid_ts_utc)
