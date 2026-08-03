{{ config(
    materialized='view'
) }}

-- ── mart_city_score_detail_v2 ───────────────────────────────────────────────
-- Exposes nullable factor scores and explicit availability metadata for the
-- worst scored date in the current two-date UTC calendar window.
--
-- Grain      : one deterministic row per city.
-- Depends on : mart_city_score_history_v2.
-- Consumers  : GET /data/city/{city_id}/scores (FastAPI).
-- ───────────────────────────────────────────────────────────────────────────────

WITH current_window AS (
    SELECT *
    FROM {{ ref('mart_city_score_history_v2') }}
    WHERE date BETWEEN CURRENT_DATE('UTC')
        AND DATE_ADD(CURRENT_DATE('UTC'), INTERVAL 1 DAY)
),

worst_day AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY city_id
            ORDER BY global_score_available DESC, global_tipping_score DESC, date ASC
        ) AS _row_number
    FROM current_window
)

SELECT
    operational_ingestion_run_id,
    operational_ingested_at_utc,
    run_has_weather_source,
    run_has_air_quality_source,
    run_has_flood_source,
    run_has_historical_weather_source,
    run_source_count,
    city_id,
    date AS score_date,
    global_tipping_score AS current_tipping_score,
    primary_driver AS current_primary_driver,
    global_score_available AS current_score_available,
    monitored_factor_count,
    available_factor_count,
    overall_coverage,

    weather_source_available,
    weather_ingested_at_utc,
    air_quality_source_available,
    air_quality_ingested_at_utc,
    flood_source_available,
    flood_ingested_at_utc,

    heat_score,
    heat_status,
    heat_monitored,
    heat_available,
    heat_coverage,
    wind_score,
    wind_status,
    wind_monitored,
    wind_available,
    wind_coverage,
    rain_score,
    rain_status,
    rain_monitored,
    rain_available,
    rain_coverage,
    air_score,
    air_status,
    air_monitored,
    air_available,
    air_coverage,
    river_score,
    river_status,
    river_monitored,
    river_available,
    river_coverage,

    temperature_2m_max,
    wind_gusts_10m_max,
    precipitation_sum_mm,
    european_aqi_max,
    river_discharge_m3s

FROM worst_day
WHERE _row_number = 1
ORDER BY current_score_available DESC, current_tipping_score DESC
