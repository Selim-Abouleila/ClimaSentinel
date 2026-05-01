-- stg_city_signal_input.sql
-- ⭐ Key deliverable of the Silver layer.
-- Joins all five deduplicated & aggregated signal sources into a single unified
-- row per (city_id, date). This is the sole input table for the Gold/mart layer
-- where tipping-score computation happens.
--
-- Grain: one row per city per date.
-- River discharge is nullable (only available for river-enabled cities).
-- Historical weather is nullable (ERA5 has a ~5-day publication lag).

SELECT
    w.city_id,
    w.date,

    -- ── Weather signals (from forecast, aggregated hourly→daily) ─────────
    w.temperature_2m_mean,
    w.temperature_2m_max,
    w.temperature_2m_min,
    w.precipitation_sum_mm,
    w.wind_speed_10m_max,
    w.wind_gusts_10m_max,
    w.weather_code_max,

    -- ── Air quality signals (aggregated hourly→daily) ────────────────────
    aq.european_aqi_mean,
    aq.european_aqi_max,
    aq.pm2_5_mean,
    aq.pm10_mean,
    aq.no2_mean,
    aq.o3_mean,

    -- ── River discharge (nullable — only river-enabled cities) ───────────
    fl.river_discharge_m3s,

    -- ── Historical baseline (nullable — ERA5 lag) ────────────────────────
    h.temperature_2m_mean   AS hist_temperature_2m_mean,
    h.temperature_2m_max    AS hist_temperature_2m_max,
    h.temperature_2m_min    AS hist_temperature_2m_min,
    h.precipitation_sum_mm  AS hist_precipitation_sum_mm,
    h.wind_speed_10m_max    AS hist_wind_speed_10m_max

FROM      {{ ref('stg_city_daily_weather') }}          w
LEFT JOIN {{ ref('stg_city_daily_air_quality') }}      aq USING (city_id, date)
LEFT JOIN {{ ref('stg_latest_flood_daily') }}          fl USING (city_id, date)
LEFT JOIN {{ ref('stg_latest_historical_daily') }}     h  USING (city_id, date)
