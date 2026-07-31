{{ config(tags=['forecast_vintage']) }}

-- Exact retry duplicates are safe to collapse. Conflicting payloads for the
-- same raw vintage key are not: they make the canonical row ambiguous and must
-- fail validation instead of being silently hidden by ROW_NUMBER.

WITH violations AS (
    SELECT
        'raw.weather_forecast_hourly' AS source_name,
        ingestion_run_id,
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
        SELECT city_id FROM {{ ref('forecast_city_allowlist') }}
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
        ingestion_run_id,
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
        SELECT city_id FROM {{ ref('forecast_city_allowlist') }}
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
        ingestion_run_id,
        city_id,
        CAST(date AS STRING),
        COUNT(*),
        COUNT(DISTINCT TO_JSON_STRING(STRUCT(
            river_discharge_m3s AS river_discharge_m3s
        )))
    FROM {{ source('raw', 'flood_daily') }}
    WHERE city_id IN (
        SELECT city_id FROM {{ ref('forecast_city_allowlist') }}
    )
    GROUP BY ingestion_run_id, city_id, date
    HAVING COUNT(DISTINCT TO_JSON_STRING(STRUCT(
        river_discharge_m3s AS river_discharge_m3s
    ))) > 1
)

SELECT *
FROM violations
