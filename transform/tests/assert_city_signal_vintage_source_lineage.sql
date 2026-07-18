{{ config(tags=['forecast_vintage']) }}

-- The unified view must be a lossless projection of its exact same-vintage
-- weather, AQ, and flood source rows. BigQuery can independently evaluate the
-- FLOAT64 aggregates behind two references to the same view, so floating-point
-- payloads use a null-safe tolerance instead of exact equality.

WITH joined AS (
    SELECT
        s.*,

        w.ingestion_run_id AS source_weather_run_id,
        w.ingested_at_utc AS source_weather_ingested_at_utc,
        w.forecast_origin_time_zone AS source_weather_time_zone,
        w.forecast_origin_date AS source_weather_origin_date,
        w.horizon_days AS source_weather_horizon_days,
        w.temperature_2m_mean AS source_temperature_2m_mean,
        w.temperature_2m_max AS source_temperature_2m_max,
        w.temperature_2m_min AS source_temperature_2m_min,
        w.precipitation_sum_mm AS source_precipitation_sum_mm,
        w.wind_speed_10m_max AS source_wind_speed_10m_max,
        w.wind_gusts_10m_max AS source_wind_gusts_10m_max,
        w.weather_code_max AS source_weather_code_max,
        w.hour_count AS source_weather_hour_count,
        w.distinct_hour_count AS source_weather_distinct_hour_count,
        w.temperature_reading_count AS source_temperature_reading_count,
        w.precipitation_reading_count AS source_precipitation_reading_count,
        w.wind_speed_reading_count AS source_wind_speed_reading_count,
        w.wind_gusts_reading_count AS source_wind_gusts_reading_count,
        w.weather_code_reading_count AS source_weather_code_reading_count,
        w.has_24_hour_coverage AS source_weather_has_24_hour_coverage,
        w.has_complete_weather_values AS source_has_complete_weather_values,

        aq.ingestion_run_id AS source_aq_run_id,
        aq.ingested_at_utc AS source_aq_ingested_at_utc,
        aq.forecast_origin_time_zone AS source_aq_time_zone,
        aq.forecast_origin_date AS source_aq_origin_date,
        aq.horizon_days AS source_aq_horizon_days,
        aq.european_aqi_mean AS source_european_aqi_mean,
        aq.european_aqi_max AS source_european_aqi_max,
        aq.pm2_5_mean AS source_pm2_5_mean,
        aq.pm10_mean AS source_pm10_mean,
        aq.no2_mean AS source_no2_mean,
        aq.o3_mean AS source_o3_mean,
        aq.hour_count AS source_aq_hour_count,
        aq.distinct_hour_count AS source_aq_distinct_hour_count,
        aq.european_aqi_reading_count AS source_european_aqi_reading_count,
        aq.pm2_5_reading_count AS source_pm2_5_reading_count,
        aq.pm10_reading_count AS source_pm10_reading_count,
        aq.no2_reading_count AS source_no2_reading_count,
        aq.o3_reading_count AS source_o3_reading_count,
        aq.has_24_hour_coverage AS source_aq_has_24_hour_coverage,
        aq.has_complete_air_quality_values AS source_has_complete_aq_values,

        fl.ingestion_run_id AS source_flood_run_id,
        fl.ingested_at_utc AS source_flood_ingested_at_utc,
        fl.forecast_origin_time_zone AS source_flood_time_zone,
        fl.forecast_origin_date AS source_flood_origin_date,
        fl.horizon_days AS source_flood_horizon_days,
        fl.river_discharge_m3s AS source_river_discharge_m3s

    FROM {{ ref('stg_city_signal_vintage') }} s
    LEFT JOIN {{ ref('stg_city_daily_weather_vintage') }} w
        ON s.ingestion_run_id = w.ingestion_run_id
        AND s.city_id = w.city_id
        AND s.valid_date = w.valid_date
    LEFT JOIN {{ ref('stg_city_daily_air_quality_vintage') }} aq
        ON s.ingestion_run_id = aq.ingestion_run_id
        AND s.city_id = aq.city_id
        AND s.valid_date = aq.valid_date
    LEFT JOIN {{ ref('stg_flood_daily_vintage') }} fl
        ON s.ingestion_run_id = fl.ingestion_run_id
        AND s.city_id = fl.city_id
        AND s.valid_date = fl.valid_date
)

SELECT
    ingestion_run_id,
    city_id,
    valid_date,
    ingested_at_utc,
    forecast_origin_time_zone,
    forecast_origin_date,
    horizon_days,
    has_air_quality_forecast,
    has_flood_forecast
FROM joined
WHERE
    -- Weather is the mandatory anchor.
    source_weather_run_id IS NULL
    OR ingested_at_utc IS DISTINCT FROM source_weather_ingested_at_utc
    OR forecast_origin_time_zone IS DISTINCT FROM source_weather_time_zone
    OR forecast_origin_date IS DISTINCT FROM source_weather_origin_date
    OR horizon_days IS DISTINCT FROM source_weather_horizon_days
    OR (temperature_2m_mean IS NULL) != (source_temperature_2m_mean IS NULL)
    OR COALESCE(ABS(temperature_2m_mean - source_temperature_2m_mean) > 1e-6, FALSE)
    OR (temperature_2m_max IS NULL) != (source_temperature_2m_max IS NULL)
    OR COALESCE(ABS(temperature_2m_max - source_temperature_2m_max) > 1e-6, FALSE)
    OR (temperature_2m_min IS NULL) != (source_temperature_2m_min IS NULL)
    OR COALESCE(ABS(temperature_2m_min - source_temperature_2m_min) > 1e-6, FALSE)
    OR (precipitation_sum_mm IS NULL) != (source_precipitation_sum_mm IS NULL)
    OR COALESCE(ABS(precipitation_sum_mm - source_precipitation_sum_mm) > 1e-6, FALSE)
    OR (wind_speed_10m_max IS NULL) != (source_wind_speed_10m_max IS NULL)
    OR COALESCE(ABS(wind_speed_10m_max - source_wind_speed_10m_max) > 1e-6, FALSE)
    OR (wind_gusts_10m_max IS NULL) != (source_wind_gusts_10m_max IS NULL)
    OR COALESCE(ABS(wind_gusts_10m_max - source_wind_gusts_10m_max) > 1e-6, FALSE)
    OR weather_code_max IS DISTINCT FROM source_weather_code_max
    OR weather_hour_count IS DISTINCT FROM source_weather_hour_count
    OR weather_distinct_hour_count IS DISTINCT FROM source_weather_distinct_hour_count
    OR temperature_reading_count IS DISTINCT FROM source_temperature_reading_count
    OR precipitation_reading_count IS DISTINCT FROM source_precipitation_reading_count
    OR wind_speed_reading_count IS DISTINCT FROM source_wind_speed_reading_count
    OR wind_gusts_reading_count IS DISTINCT FROM source_wind_gusts_reading_count
    OR weather_code_reading_count IS DISTINCT FROM source_weather_code_reading_count
    OR weather_has_24_hour_coverage IS DISTINCT FROM source_weather_has_24_hour_coverage
    OR has_complete_weather_values IS DISTINCT FROM source_has_complete_weather_values

    -- AQ is optional, but its presence flag, metadata, values, and coverage
    -- columns must all match the exact same-vintage source row.
    OR has_air_quality_forecast IS DISTINCT FROM (source_aq_run_id IS NOT NULL)
    OR air_quality_ingested_at_utc IS DISTINCT FROM source_aq_ingested_at_utc
    OR (
        source_aq_run_id IS NOT NULL
        AND (
            ingested_at_utc IS DISTINCT FROM source_aq_ingested_at_utc
            OR forecast_origin_time_zone IS DISTINCT FROM source_aq_time_zone
            OR forecast_origin_date IS DISTINCT FROM source_aq_origin_date
            OR horizon_days IS DISTINCT FROM source_aq_horizon_days
        )
    )
    OR (european_aqi_mean IS NULL) != (source_european_aqi_mean IS NULL)
    OR COALESCE(ABS(european_aqi_mean - source_european_aqi_mean) > 1e-6, FALSE)
    OR (european_aqi_max IS NULL) != (source_european_aqi_max IS NULL)
    OR COALESCE(ABS(european_aqi_max - source_european_aqi_max) > 1e-6, FALSE)
    OR (pm2_5_mean IS NULL) != (source_pm2_5_mean IS NULL)
    OR COALESCE(ABS(pm2_5_mean - source_pm2_5_mean) > 1e-6, FALSE)
    OR (pm10_mean IS NULL) != (source_pm10_mean IS NULL)
    OR COALESCE(ABS(pm10_mean - source_pm10_mean) > 1e-6, FALSE)
    OR (no2_mean IS NULL) != (source_no2_mean IS NULL)
    OR COALESCE(ABS(no2_mean - source_no2_mean) > 1e-6, FALSE)
    OR (o3_mean IS NULL) != (source_o3_mean IS NULL)
    OR COALESCE(ABS(o3_mean - source_o3_mean) > 1e-6, FALSE)
    OR air_quality_hour_count IS DISTINCT FROM source_aq_hour_count
    OR air_quality_distinct_hour_count IS DISTINCT FROM source_aq_distinct_hour_count
    OR european_aqi_reading_count IS DISTINCT FROM source_european_aqi_reading_count
    OR pm2_5_reading_count IS DISTINCT FROM source_pm2_5_reading_count
    OR pm10_reading_count IS DISTINCT FROM source_pm10_reading_count
    OR no2_reading_count IS DISTINCT FROM source_no2_reading_count
    OR o3_reading_count IS DISTINCT FROM source_o3_reading_count
    OR air_quality_has_24_hour_coverage IS DISTINCT FROM source_aq_has_24_hour_coverage
    OR has_complete_air_quality_values IS DISTINCT FROM source_has_complete_aq_values

    -- Flood is optional and follows the same exact-vintage rules.
    OR has_flood_forecast IS DISTINCT FROM (source_flood_run_id IS NOT NULL)
    OR flood_ingested_at_utc IS DISTINCT FROM source_flood_ingested_at_utc
    OR (
        source_flood_run_id IS NOT NULL
        AND (
            ingested_at_utc IS DISTINCT FROM source_flood_ingested_at_utc
            OR forecast_origin_time_zone IS DISTINCT FROM source_flood_time_zone
            OR forecast_origin_date IS DISTINCT FROM source_flood_origin_date
            OR horizon_days IS DISTINCT FROM source_flood_horizon_days
        )
    )
    OR (river_discharge_m3s IS NULL) != (source_river_discharge_m3s IS NULL)
    OR COALESCE(ABS(river_discharge_m3s - source_river_discharge_m3s) > 1e-6, FALSE)
