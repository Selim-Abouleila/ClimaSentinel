-- The v2 path may collapse exact retry duplicates, but conflicting payloads
-- for the same raw key and run must fail instead of being hidden by ROW_NUMBER.
-- Scope covers every operational monitoring city, not only the forecast allowlist.

WITH violations AS (
    SELECT
        'raw.weather_forecast_hourly' AS source_name,
        CAST(ingestion_run_id AS STRING) AS ingestion_run_id,
        city_id,
        CAST(valid_ts_utc AS STRING) AS valid_key,
        COUNT(*) AS raw_row_count,
        COUNT(DISTINCT TO_JSON_STRING(STRUCT(
            temperature_2m AS temperature_2m,
            precipitation_mm AS precipitation_mm,
            wind_speed_10m AS wind_speed_10m,
            wind_gusts_10m AS wind_gusts_10m,
            weather_code AS weather_code
        ))) AS payload_variant_count
    FROM {{ source('raw', 'weather_forecast_hourly') }}
    WHERE city_id IN (
        SELECT city_id FROM {{ ref('city_signal_monitoring') }}
    )
    GROUP BY ingestion_run_id, city_id, valid_ts_utc
    HAVING COUNT(DISTINCT TO_JSON_STRING(STRUCT(
        temperature_2m AS temperature_2m,
        precipitation_mm AS precipitation_mm,
        wind_speed_10m AS wind_speed_10m,
        wind_gusts_10m AS wind_gusts_10m,
        weather_code AS weather_code
    ))) > 1

    UNION ALL

    SELECT
        'raw.air_quality_hourly',
        CAST(ingestion_run_id AS STRING),
        city_id,
        CAST(valid_ts_utc AS STRING),
        COUNT(*),
        COUNT(DISTINCT TO_JSON_STRING(STRUCT(
            european_aqi AS european_aqi,
            pm2_5 AS pm2_5,
            pm10 AS pm10,
            no2 AS no2,
            o3 AS o3
        )))
    FROM {{ source('raw', 'air_quality_hourly') }}
    WHERE city_id IN (
        SELECT city_id FROM {{ ref('city_signal_monitoring') }}
    )
    GROUP BY ingestion_run_id, city_id, valid_ts_utc
    HAVING COUNT(DISTINCT TO_JSON_STRING(STRUCT(
        european_aqi AS european_aqi,
        pm2_5 AS pm2_5,
        pm10 AS pm10,
        no2 AS no2,
        o3 AS o3
    ))) > 1

    UNION ALL

    SELECT
        'raw.flood_daily',
        CAST(ingestion_run_id AS STRING),
        city_id,
        CAST(date AS STRING),
        COUNT(*),
        COUNT(DISTINCT TO_JSON_STRING(STRUCT(
            river_discharge_m3s AS river_discharge_m3s
        )))
    FROM {{ source('raw', 'flood_daily') }}
    WHERE city_id IN (
        SELECT city_id FROM {{ ref('city_signal_monitoring') }}
    )
    GROUP BY ingestion_run_id, city_id, date
    HAVING COUNT(DISTINCT TO_JSON_STRING(STRUCT(
        river_discharge_m3s AS river_discharge_m3s
    ))) > 1
)

SELECT *
FROM violations
