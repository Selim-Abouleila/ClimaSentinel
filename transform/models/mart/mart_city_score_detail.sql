{{ config(
    materialized='view'
) }}

-- ── mart_city_score_detail ────────────────────────────────────────────────
-- Exposes the five individual tipping sub-scores (heat, wind, rain, air,
-- river) for every city within the current 48-hour operational window.
--
-- Grain      : one row per city (the day with the highest global score wins).
-- Depends on : mart_city_score_history  (NOT mart_city_score_current — kept
--              fully independent so existing dashboard is unaffected).
-- Consumers  : GET /data/city/{city_id}/scores  (FastAPI)
-- ─────────────────────────────────────────────────────────────────────────

WITH current_window AS (
    SELECT
        city_id,
        date,

        -- Global composite
        global_tipping_score,
        primary_driver,

        -- ── Individual sub-scores (0–100 each) ───────────────────────────
        heat_score,
        wind_score,
        rain_score,
        air_score,
        river_score,

        -- ── Raw signal context ────────────────────────────────────────────
        temperature_2m_max,
        wind_gusts_10m_max,
        precipitation_sum_mm,
        european_aqi_max,
        river_discharge_m3s

    FROM {{ ref('mart_city_score_history') }}
    -- Same 48-hour window used by mart_city_score_current
    WHERE date BETWEEN CURRENT_DATE('UTC') AND DATE_ADD(CURRENT_DATE('UTC'), INTERVAL 1 DAY)
),

-- For each city pick the single day that produced the highest global score.
-- All sub-scores, raw values, and the primary driver come from that same day.
worst_day AS (
    SELECT
        city_id,

        -- Global
        ANY_VALUE(global_tipping_score HAVING MAX global_tipping_score) AS current_tipping_score,
        ANY_VALUE(primary_driver       HAVING MAX global_tipping_score) AS current_primary_driver,

        -- Sub-scores on the worst day
        ANY_VALUE(heat_score           HAVING MAX global_tipping_score) AS heat_score,
        ANY_VALUE(wind_score           HAVING MAX global_tipping_score) AS wind_score,
        ANY_VALUE(rain_score           HAVING MAX global_tipping_score) AS rain_score,
        ANY_VALUE(air_score            HAVING MAX global_tipping_score) AS air_score,
        ANY_VALUE(river_score          HAVING MAX global_tipping_score) AS river_score,

        -- Raw signals on the worst day (for tooltip context in the UI)
        ANY_VALUE(temperature_2m_max   HAVING MAX global_tipping_score) AS temperature_2m_max,
        ANY_VALUE(wind_gusts_10m_max   HAVING MAX global_tipping_score) AS wind_gusts_10m_max,
        ANY_VALUE(precipitation_sum_mm HAVING MAX global_tipping_score) AS precipitation_sum_mm,
        ANY_VALUE(european_aqi_max     HAVING MAX global_tipping_score) AS european_aqi_max,
        ANY_VALUE(river_discharge_m3s  HAVING MAX global_tipping_score) AS river_discharge_m3s

    FROM current_window
    GROUP BY city_id
)

SELECT
    city_id,
    current_tipping_score,
    current_primary_driver,
    heat_score,
    wind_score,
    rain_score,
    air_score,
    river_score,
    temperature_2m_max,
    wind_gusts_10m_max,
    precipitation_sum_mm,
    european_aqi_max,
    river_discharge_m3s
FROM worst_day
ORDER BY current_tipping_score DESC
