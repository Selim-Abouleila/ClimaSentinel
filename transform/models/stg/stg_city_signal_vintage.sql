{{ config(tags=['forecast_vintage']) }}

-- Unified point-in-time forecast signal view.
--
-- Grain: one row per (ingestion_run_id, city_id, valid_date), anchored on the
-- weather snapshot. AQ and flood can only join from the exact same ingestion
-- run, city, and valid date. A failed source therefore remains visibly absent
-- instead of silently falling back to another forecast vintage.
--
-- ERA5 history is intentionally excluded: it is a later realized-label source,
-- not a forecast feature available in the same vintage.

SELECT
    w.ingestion_run_id,
    w.ingested_at_utc,
    w.forecast_origin_time_zone,
    w.forecast_origin_date,
    w.city_id,
    w.valid_date,
    w.horizon_days,

    -- Weather forecast values
    w.temperature_2m_mean,
    w.temperature_2m_max,
    w.temperature_2m_min,
    w.precipitation_sum_mm,
    w.wind_speed_10m_max,
    w.wind_gusts_10m_max,
    w.weather_code_max,

    -- Air-quality forecast values from the same vintage
    aq.european_aqi_mean,
    aq.european_aqi_max,
    aq.pm2_5_mean,
    aq.pm10_mean,
    aq.no2_mean,
    aq.o3_mean,

    -- River forecast value from the same vintage, when applicable
    fl.river_discharge_m3s,

    -- Source presence and daily coverage metadata
    w.hour_count AS weather_hour_count,
    w.distinct_hour_count AS weather_distinct_hour_count,
    w.temperature_reading_count,
    w.precipitation_reading_count,
    w.wind_speed_reading_count,
    w.wind_gusts_reading_count,
    w.weather_code_reading_count,
    w.has_24_hour_coverage AS weather_has_24_hour_coverage,
    w.has_complete_weather_values,

    aq.hour_count AS air_quality_hour_count,
    aq.distinct_hour_count AS air_quality_distinct_hour_count,
    aq.european_aqi_reading_count,
    aq.pm2_5_reading_count,
    aq.pm10_reading_count,
    aq.no2_reading_count,
    aq.o3_reading_count,
    aq.has_24_hour_coverage AS air_quality_has_24_hour_coverage,
    aq.has_complete_air_quality_values,

    aq.ingestion_run_id IS NOT NULL AS has_air_quality_forecast,
    fl.ingestion_run_id IS NOT NULL AS has_flood_forecast,
    aq.ingested_at_utc AS air_quality_ingested_at_utc,
    fl.ingested_at_utc AS flood_ingested_at_utc

FROM {{ ref('stg_city_daily_weather_vintage') }} w
LEFT JOIN {{ ref('stg_city_daily_air_quality_vintage') }} aq
    ON w.ingestion_run_id = aq.ingestion_run_id
    AND w.ingested_at_utc = aq.ingested_at_utc
    AND w.forecast_origin_time_zone = aq.forecast_origin_time_zone
    AND w.forecast_origin_date = aq.forecast_origin_date
    AND w.city_id = aq.city_id
    AND w.valid_date = aq.valid_date
    AND w.horizon_days = aq.horizon_days
LEFT JOIN {{ ref('stg_flood_daily_vintage') }} fl
    ON w.ingestion_run_id = fl.ingestion_run_id
    AND w.ingested_at_utc = fl.ingested_at_utc
    AND w.forecast_origin_time_zone = fl.forecast_origin_time_zone
    AND w.forecast_origin_date = fl.forecast_origin_date
    AND w.city_id = fl.city_id
    AND w.valid_date = fl.valid_date
    AND w.horizon_days = fl.horizon_days
