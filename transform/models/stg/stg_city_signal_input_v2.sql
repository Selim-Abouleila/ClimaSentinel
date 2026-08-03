{{ config(
    materialized='view'
) }}

-- Exact-run operational signal spine. Every monitoring city receives every
-- date present in the selected forecast-source snapshot plus today through Day +2.
-- Day +2 is required to score tomorrow's Heat/River velocity without fallback.

WITH selected_run AS (
    SELECT *
    FROM {{ ref('stg_operational_run_v2') }}
),

run_dates AS (
    SELECT DISTINCT date
    FROM {{ ref('stg_city_daily_weather_v2') }}

    UNION DISTINCT

    SELECT DISTINCT date
    FROM {{ ref('stg_city_daily_air_quality_v2') }}

    UNION DISTINCT

    SELECT DISTINCT date
    FROM {{ ref('stg_flood_daily_v2') }}
),

required_dates AS (
    SELECT operational_date AS date
    FROM UNNEST(
        GENERATE_DATE_ARRAY(
            CURRENT_DATE('UTC'),
            DATE_ADD(CURRENT_DATE('UTC'), INTERVAL 2 DAY)
        )
    ) AS operational_date
),

operational_dates AS (
    SELECT date FROM run_dates
    UNION DISTINCT
    SELECT date FROM required_dates
),

city_date_spine AS (
    SELECT
        monitoring.city_id,
        operational_dates.date,
        monitoring.heat_monitored,
        monitoring.wind_monitored,
        monitoring.rain_monitored,
        monitoring.air_monitored,
        monitoring.river_monitored
    FROM {{ ref('city_signal_monitoring') }} AS monitoring
    CROSS JOIN operational_dates
)

SELECT
    selected_run.operational_ingestion_run_id,
    selected_run.operational_ingested_at_utc,
    selected_run.run_has_weather_source,
    selected_run.run_has_air_quality_source,
    selected_run.run_has_flood_source,
    selected_run.run_has_historical_weather_source,
    selected_run.run_source_count,

    spine.city_id,
    spine.date,
    spine.heat_monitored,
    spine.wind_monitored,
    spine.rain_monitored,
    spine.air_monitored,
    spine.river_monitored,

    weather.ingestion_run_id IS NOT NULL AS weather_source_available,
    weather.weather_ingested_at_utc,
    weather.temperature_2m_mean,
    weather.temperature_2m_max,
    weather.temperature_2m_min,
    weather.precipitation_sum_mm,
    weather.wind_speed_10m_max,
    weather.wind_gusts_10m_max,
    weather.weather_code_max,
    COALESCE(weather.weather_hour_count, 0) AS weather_hour_count,
    COALESCE(weather.temperature_2m_value_count, 0)
        AS temperature_2m_value_count,
    COALESCE(weather.precipitation_value_count, 0)
        AS precipitation_value_count,
    COALESCE(weather.wind_speed_10m_value_count, 0)
        AS wind_speed_10m_value_count,
    COALESCE(weather.wind_gusts_10m_value_count, 0)
        AS wind_gusts_10m_value_count,

    air_quality.ingestion_run_id IS NOT NULL AS air_quality_source_available,
    air_quality.air_quality_ingested_at_utc,
    air_quality.european_aqi_mean,
    air_quality.european_aqi_max,
    air_quality.pm2_5_mean,
    air_quality.pm10_mean,
    air_quality.no2_mean,
    air_quality.o3_mean,
    COALESCE(air_quality.air_quality_hour_count, 0)
        AS air_quality_hour_count,
    COALESCE(air_quality.european_aqi_value_count, 0)
        AS european_aqi_value_count,

    flood.ingestion_run_id IS NOT NULL AS flood_source_available,
    flood.flood_ingested_at_utc,
    flood.river_discharge_m3s

FROM city_date_spine AS spine
CROSS JOIN selected_run
LEFT JOIN {{ ref('stg_city_daily_weather_v2') }} AS weather
    ON spine.city_id = weather.city_id
    AND spine.date = weather.date
    AND selected_run.operational_ingestion_run_id = weather.ingestion_run_id
LEFT JOIN {{ ref('stg_city_daily_air_quality_v2') }} AS air_quality
    ON spine.city_id = air_quality.city_id
    AND spine.date = air_quality.date
    AND selected_run.operational_ingestion_run_id = air_quality.ingestion_run_id
LEFT JOIN {{ ref('stg_flood_daily_v2') }} AS flood
    ON spine.city_id = flood.city_id
    AND spine.date = flood.date
    AND selected_run.operational_ingestion_run_id = flood.ingestion_run_id
