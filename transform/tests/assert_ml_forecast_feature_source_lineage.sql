{{ config(tags=['ml_point_in_time']) }}

-- Every source run/city/origin group with a Horizon 0-4 row must appear in the
-- wide feature ledger. Each horizon must retain the exact source metadata,
-- deterministic payloads, and presence/coverage flags from that same vintage.
-- Precipitation is a two-decimal, SUM-derived FLOAT64, so it is compared by
-- NULL shape and a 0.011 tolerance rather than brittle bit-for-bit equality
-- across independently expanded BigQuery views.

WITH all_source_signal AS (
    SELECT *
    FROM {{ ref('stg_city_signal_vintage') }}
),

source_signal AS (
    SELECT *
    FROM source_signal
    WHERE horizon_days BETWEEN 0 AND 4
),

source_groups AS (
    SELECT
        ingestion_run_id,
        city_id,
        forecast_origin_date,
        MIN(ingested_at_utc) AS ingested_at_utc,
        ANY_VALUE(forecast_origin_time_zone) AS forecast_origin_time_zone
    FROM all_source_signal
    GROUP BY ingestion_run_id, city_id, forecast_origin_date
),

source_lattice AS (
    SELECT
        g.*,
        horizon_days
    FROM source_groups g
    CROSS JOIN UNNEST(GENERATE_ARRAY(0, 4)) AS horizon_days
),

feature_horizons AS (
    SELECT
        ingestion_run_id,
        city_id,
        forecast_origin_date,
        ingested_at_utc,
        forecast_origin_time_zone,
        0 AS horizon_days,
        has_horizon_0d AS has_horizon,
        valid_date_0d AS valid_date,
        temperature_2m_max,
        temperature_2m_min,
        precipitation_sum_mm,
        wind_speed_10m_max,
        wind_gusts_10m_max,
        european_aqi_max,
        river_discharge_m3s,
        weather_has_24_hour_coverage_0d AS weather_has_24_hour_coverage,
        has_complete_weather_values_0d AS has_complete_weather_values,
        has_air_quality_forecast_0d AS has_air_quality_forecast,
        air_quality_has_24_hour_coverage_0d AS air_quality_has_24_hour_coverage,
        has_complete_air_quality_values_0d AS has_complete_air_quality_values,
        has_flood_forecast_0d AS has_flood_forecast
    FROM {{ ref('mart_ml_forecast_features_vintage') }}

    UNION ALL

    SELECT
        ingestion_run_id,
        city_id,
        forecast_origin_date,
        ingested_at_utc,
        forecast_origin_time_zone,
        1 AS horizon_days,
        has_horizon_plus_1d AS has_horizon,
        valid_date_plus_1d AS valid_date,
        temp_forecast_plus_1d AS temperature_2m_max,
        CAST(NULL AS FLOAT64) AS temperature_2m_min,
        precip_forecast_plus_1d AS precipitation_sum_mm,
        wind_forecast_plus_1d AS wind_speed_10m_max,
        wind_gusts_forecast_plus_1d AS wind_gusts_10m_max,
        aqi_forecast_plus_1d AS european_aqi_max,
        river_forecast_plus_1d AS river_discharge_m3s,
        weather_has_24_hour_coverage_plus_1d AS weather_has_24_hour_coverage,
        has_complete_weather_values_plus_1d AS has_complete_weather_values,
        has_air_quality_forecast_plus_1d AS has_air_quality_forecast,
        air_quality_has_24_hour_coverage_plus_1d AS air_quality_has_24_hour_coverage,
        has_complete_air_quality_values_plus_1d AS has_complete_air_quality_values,
        has_flood_forecast_plus_1d AS has_flood_forecast
    FROM {{ ref('mart_ml_forecast_features_vintage') }}

    UNION ALL

    SELECT
        ingestion_run_id,
        city_id,
        forecast_origin_date,
        ingested_at_utc,
        forecast_origin_time_zone,
        2 AS horizon_days,
        has_horizon_plus_2d AS has_horizon,
        valid_date_plus_2d AS valid_date,
        temp_forecast_plus_2d AS temperature_2m_max,
        CAST(NULL AS FLOAT64) AS temperature_2m_min,
        precip_forecast_plus_2d AS precipitation_sum_mm,
        wind_forecast_plus_2d AS wind_speed_10m_max,
        wind_gusts_forecast_plus_2d AS wind_gusts_10m_max,
        aqi_forecast_plus_2d AS european_aqi_max,
        river_forecast_plus_2d AS river_discharge_m3s,
        weather_has_24_hour_coverage_plus_2d AS weather_has_24_hour_coverage,
        has_complete_weather_values_plus_2d AS has_complete_weather_values,
        has_air_quality_forecast_plus_2d AS has_air_quality_forecast,
        air_quality_has_24_hour_coverage_plus_2d AS air_quality_has_24_hour_coverage,
        has_complete_air_quality_values_plus_2d AS has_complete_air_quality_values,
        has_flood_forecast_plus_2d AS has_flood_forecast
    FROM {{ ref('mart_ml_forecast_features_vintage') }}

    UNION ALL

    SELECT
        ingestion_run_id,
        city_id,
        forecast_origin_date,
        ingested_at_utc,
        forecast_origin_time_zone,
        3 AS horizon_days,
        has_horizon_plus_3d AS has_horizon,
        valid_date_plus_3d AS valid_date,
        temp_forecast_plus_3d AS temperature_2m_max,
        CAST(NULL AS FLOAT64) AS temperature_2m_min,
        precip_forecast_plus_3d AS precipitation_sum_mm,
        wind_forecast_plus_3d AS wind_speed_10m_max,
        wind_gusts_forecast_plus_3d AS wind_gusts_10m_max,
        aqi_forecast_plus_3d AS european_aqi_max,
        river_forecast_plus_3d AS river_discharge_m3s,
        weather_has_24_hour_coverage_plus_3d AS weather_has_24_hour_coverage,
        has_complete_weather_values_plus_3d AS has_complete_weather_values,
        has_air_quality_forecast_plus_3d AS has_air_quality_forecast,
        air_quality_has_24_hour_coverage_plus_3d AS air_quality_has_24_hour_coverage,
        has_complete_air_quality_values_plus_3d AS has_complete_air_quality_values,
        has_flood_forecast_plus_3d AS has_flood_forecast
    FROM {{ ref('mart_ml_forecast_features_vintage') }}

    UNION ALL

    SELECT
        ingestion_run_id,
        city_id,
        forecast_origin_date,
        ingested_at_utc,
        forecast_origin_time_zone,
        4 AS horizon_days,
        has_horizon_plus_4d AS has_horizon,
        valid_date_plus_4d AS valid_date,
        temp_forecast_plus_4d AS temperature_2m_max,
        CAST(NULL AS FLOAT64) AS temperature_2m_min,
        CAST(NULL AS FLOAT64) AS precipitation_sum_mm,
        CAST(NULL AS FLOAT64) AS wind_speed_10m_max,
        CAST(NULL AS FLOAT64) AS wind_gusts_10m_max,
        CAST(NULL AS FLOAT64) AS european_aqi_max,
        river_forecast_plus_4d AS river_discharge_m3s,
        weather_has_24_hour_coverage_plus_4d AS weather_has_24_hour_coverage,
        has_complete_weather_values_plus_4d AS has_complete_weather_values,
        has_air_quality_forecast_plus_4d AS has_air_quality_forecast,
        air_quality_has_24_hour_coverage_plus_4d AS air_quality_has_24_hour_coverage,
        has_complete_air_quality_values_plus_4d AS has_complete_air_quality_values,
        has_flood_forecast_plus_4d AS has_flood_forecast
    FROM {{ ref('mart_ml_forecast_features_vintage') }}
)

SELECT
    lattice.ingestion_run_id,
    lattice.city_id,
    lattice.forecast_origin_date,
    lattice.horizon_days
FROM source_lattice lattice
LEFT JOIN source_signal source
    ON lattice.ingestion_run_id = source.ingestion_run_id
    AND lattice.city_id = source.city_id
    AND lattice.forecast_origin_date = source.forecast_origin_date
    AND lattice.horizon_days = source.horizon_days
LEFT JOIN feature_horizons feature
    ON lattice.ingestion_run_id = feature.ingestion_run_id
    AND lattice.city_id = feature.city_id
    AND lattice.forecast_origin_date = feature.forecast_origin_date
    AND lattice.horizon_days = feature.horizon_days
WHERE feature.ingestion_run_id IS NULL
    OR feature.ingested_at_utc IS DISTINCT FROM lattice.ingested_at_utc
    OR feature.forecast_origin_time_zone
        IS DISTINCT FROM lattice.forecast_origin_time_zone
    OR feature.has_horizon
        IS DISTINCT FROM (source.ingestion_run_id IS NOT NULL)
    OR feature.valid_date IS DISTINCT FROM source.valid_date
    OR feature.weather_has_24_hour_coverage IS DISTINCT FROM COALESCE(
        source.weather_has_24_hour_coverage,
        FALSE
    )
    OR feature.has_complete_weather_values IS DISTINCT FROM COALESCE(
        source.has_complete_weather_values,
        FALSE
    )
    OR feature.has_air_quality_forecast IS DISTINCT FROM COALESCE(
        source.has_air_quality_forecast,
        FALSE
    )
    OR feature.air_quality_has_24_hour_coverage IS DISTINCT FROM COALESCE(
        source.air_quality_has_24_hour_coverage,
        FALSE
    )
    OR feature.has_complete_air_quality_values IS DISTINCT FROM COALESCE(
        source.has_complete_air_quality_values,
        FALSE
    )
    OR feature.has_flood_forecast IS DISTINCT FROM COALESCE(
        source.has_flood_forecast,
        FALSE
    )
    OR feature.temperature_2m_max IS DISTINCT FROM source.temperature_2m_max
    OR (
        lattice.horizon_days = 0
        AND feature.temperature_2m_min IS DISTINCT FROM source.temperature_2m_min
    )
    OR (
        lattice.horizon_days <= 3
        AND (
            (feature.precipitation_sum_mm IS NULL)
                IS DISTINCT FROM (source.precipitation_sum_mm IS NULL)
            OR (
                feature.precipitation_sum_mm IS NOT NULL
                AND source.precipitation_sum_mm IS NOT NULL
                AND ABS(
                    feature.precipitation_sum_mm
                    - source.precipitation_sum_mm
                ) > 0.011
            )
        )
    )
    OR (
        lattice.horizon_days <= 3
        AND feature.wind_speed_10m_max
            IS DISTINCT FROM source.wind_speed_10m_max
    )
    OR (
        lattice.horizon_days <= 3
        AND feature.wind_gusts_10m_max
            IS DISTINCT FROM source.wind_gusts_10m_max
    )
    OR (
        lattice.horizon_days <= 3
        AND feature.european_aqi_max
            IS DISTINCT FROM source.european_aqi_max
    )
    OR feature.river_discharge_m3s
        IS DISTINCT FROM source.river_discharge_m3s
