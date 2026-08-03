{{ config(
    materialized='view'
) }}

-- Exact-run daily weather. Rows from an older run are never used to fill a
-- missing timestamp in the selected operational snapshot.

WITH selected_run AS (
    SELECT *
    FROM {{ ref('stg_operational_run_v2') }}
),

ranked AS (
    SELECT
        raw_weather.*,
        ROW_NUMBER() OVER (
            PARTITION BY
                raw_weather.ingestion_run_id,
                raw_weather.city_id,
                raw_weather.valid_ts_utc
            ORDER BY
                raw_weather.ingested_at_utc DESC,
                TO_JSON_STRING(STRUCT(
                    raw_weather.temperature_2m AS temperature_2m,
                    raw_weather.precipitation_mm AS precipitation_mm,
                    raw_weather.wind_speed_10m AS wind_speed_10m,
                    raw_weather.wind_gusts_10m AS wind_gusts_10m,
                    raw_weather.weather_code AS weather_code
                )) DESC
        ) AS _row_number
    FROM {{ source('raw', 'weather_forecast_hourly') }} AS raw_weather
    INNER JOIN {{ ref('city_signal_monitoring') }} AS monitoring
        ON raw_weather.city_id = monitoring.city_id
    INNER JOIN selected_run
        ON CAST(raw_weather.ingestion_run_id AS STRING)
            = selected_run.operational_ingestion_run_id
    WHERE raw_weather.valid_ts_utc IS NOT NULL
),

deduplicated AS (
    SELECT * EXCEPT (_row_number)
    FROM ranked
    WHERE _row_number = 1
)

SELECT
    CAST(ingestion_run_id AS STRING) AS ingestion_run_id,
    MAX(ingested_at_utc) AS weather_ingested_at_utc,
    city_id,
    DATE(valid_ts_utc) AS date,
    ROUND(AVG(temperature_2m), 2) AS temperature_2m_mean,
    ROUND(MAX(temperature_2m), 2) AS temperature_2m_max,
    ROUND(MIN(temperature_2m), 2) AS temperature_2m_min,
    ROUND(SUM(precipitation_mm), 2) AS precipitation_sum_mm,
    ROUND(MAX(wind_speed_10m), 2) AS wind_speed_10m_max,
    ROUND(MAX(wind_gusts_10m), 2) AS wind_gusts_10m_max,
    MAX(weather_code) AS weather_code_max,
    COUNT(*) AS weather_hour_count,
    COUNTIF(temperature_2m IS NOT NULL) AS temperature_2m_value_count,
    COUNTIF(precipitation_mm IS NOT NULL) AS precipitation_value_count,
    COUNTIF(wind_speed_10m IS NOT NULL) AS wind_speed_10m_value_count,
    COUNTIF(wind_gusts_10m IS NOT NULL) AS wind_gusts_10m_value_count
FROM deduplicated
GROUP BY ingestion_run_id, city_id, DATE(valid_ts_utc)
