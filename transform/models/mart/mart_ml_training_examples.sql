{{ config(
    materialized='table',
    partition_by={
      "field": "forecast_origin_date",
      "data_type": "date",
      "granularity": "day"
    },
    cluster_by=['city_id', 'ingestion_run_id'],
    tags=['ml_point_in_time']
) }}

-- Point-in-time-safe supervised examples for the first honest ML scope.
--
-- Grain: one row per (city_id, forecast_origin_date). The upstream canonical
-- flag deterministically chooses the latest complete exact-vintage weather
-- feature window for each city/local-origin date. This mirrors operational
-- serving, which uses the latest successful run, while preventing retries from
-- multiplying one realized outcome during training.
--
-- Only archive/reanalysis-backed Heat and Rain targets are exposed. Wind needs observed gust
-- data, air needs observed AQ, and river needs observed discharge; the current
-- forecast feeds are not silently reused as ground truth for those components.

WITH canonical_forecasts AS (
    SELECT *
    FROM {{ ref('mart_ml_forecast_features_vintage') }}
    WHERE is_canonical_daily_vintage
        AND has_expected_horizon_dates
        AND has_complete_weather_feature_window
),

labels_joined AS (
    SELECT
        f.*,

        labels_1d.valid_date AS target_date_1d,
        labels_1d.realized_temperature_2m_max AS realized_temperature_2m_max_1d,
        labels_1d.next_day_temperature_2m_max AS next_day_temperature_2m_max_1d,
        labels_1d.realized_precipitation_sum_mm AS realized_precipitation_sum_mm_1d,
        labels_1d.realized_heat_score AS future_heat_score_1d,
        labels_1d.realized_rain_score AS future_rain_score_1d,
        labels_1d.realized_weather_ingestion_run_id
            AS realized_weather_ingestion_run_id_1d,
        labels_1d.realized_weather_ingested_at_utc
            AS realized_weather_ingested_at_utc_1d,
        labels_1d.next_day_weather_ingestion_run_id
            AS next_day_weather_ingestion_run_id_1d,
        labels_1d.next_day_weather_ingested_at_utc
            AS next_day_weather_ingested_at_utc_1d,
        labels_1d.heat_label_available_at_utc AS heat_label_available_at_utc_1d,
        labels_1d.rain_label_available_at_utc AS rain_label_available_at_utc_1d,
        labels_1d.labels_available_at_utc AS labels_available_at_utc_1d,

        labels_2d.valid_date AS target_date_2d,
        labels_2d.realized_temperature_2m_max AS realized_temperature_2m_max_2d,
        labels_2d.next_day_temperature_2m_max AS next_day_temperature_2m_max_2d,
        labels_2d.realized_precipitation_sum_mm AS realized_precipitation_sum_mm_2d,
        labels_2d.realized_heat_score AS future_heat_score_2d,
        labels_2d.realized_rain_score AS future_rain_score_2d,
        labels_2d.realized_weather_ingestion_run_id
            AS realized_weather_ingestion_run_id_2d,
        labels_2d.realized_weather_ingested_at_utc
            AS realized_weather_ingested_at_utc_2d,
        labels_2d.next_day_weather_ingestion_run_id
            AS next_day_weather_ingestion_run_id_2d,
        labels_2d.next_day_weather_ingested_at_utc
            AS next_day_weather_ingested_at_utc_2d,
        labels_2d.heat_label_available_at_utc AS heat_label_available_at_utc_2d,
        labels_2d.rain_label_available_at_utc AS rain_label_available_at_utc_2d,
        labels_2d.labels_available_at_utc AS labels_available_at_utc_2d,

        labels_3d.valid_date AS target_date_3d,
        labels_3d.realized_temperature_2m_max AS realized_temperature_2m_max_3d,
        labels_3d.next_day_temperature_2m_max AS next_day_temperature_2m_max_3d,
        labels_3d.realized_precipitation_sum_mm AS realized_precipitation_sum_mm_3d,
        labels_3d.realized_heat_score AS future_heat_score_3d,
        labels_3d.realized_rain_score AS future_rain_score_3d,
        labels_3d.realized_weather_ingestion_run_id
            AS realized_weather_ingestion_run_id_3d,
        labels_3d.realized_weather_ingested_at_utc
            AS realized_weather_ingested_at_utc_3d,
        labels_3d.next_day_weather_ingestion_run_id
            AS next_day_weather_ingestion_run_id_3d,
        labels_3d.next_day_weather_ingested_at_utc
            AS next_day_weather_ingested_at_utc_3d,
        labels_3d.heat_label_available_at_utc AS heat_label_available_at_utc_3d,
        labels_3d.rain_label_available_at_utc AS rain_label_available_at_utc_3d,
        labels_3d.labels_available_at_utc AS labels_available_at_utc_3d

    FROM canonical_forecasts f
    INNER JOIN {{ ref('mart_city_realized_weather_daily') }} labels_1d
        ON f.city_id = labels_1d.city_id
        AND labels_1d.valid_date = DATE_ADD(
            f.forecast_origin_date,
            INTERVAL 1 DAY
        )
    INNER JOIN {{ ref('mart_city_realized_weather_daily') }} labels_2d
        ON f.city_id = labels_2d.city_id
        AND labels_2d.valid_date = DATE_ADD(
            f.forecast_origin_date,
            INTERVAL 2 DAY
        )
    INNER JOIN {{ ref('mart_city_realized_weather_daily') }} labels_3d
        ON f.city_id = labels_3d.city_id
        AND labels_3d.valid_date = DATE_ADD(
            f.forecast_origin_date,
            INTERVAL 3 DAY
        )
    WHERE labels_1d.has_mature_realized_labels
        AND labels_2d.has_mature_realized_labels
        AND labels_3d.has_mature_realized_labels
        -- A label may only enter an example after it became available. Strict
        -- inequalities make the anti-leakage contract unambiguous.
        AND labels_1d.heat_label_available_at_utc > f.ingested_at_utc
        AND labels_1d.rain_label_available_at_utc > f.ingested_at_utc
        AND labels_2d.heat_label_available_at_utc > f.ingested_at_utc
        AND labels_2d.rain_label_available_at_utc > f.ingested_at_utc
        AND labels_3d.heat_label_available_at_utc > f.ingested_at_utc
        AND labels_3d.rain_label_available_at_utc > f.ingested_at_utc
)

SELECT
    *,
    GREATEST(
        labels_available_at_utc_1d,
        labels_available_at_utc_2d,
        labels_available_at_utc_3d
    ) AS training_labels_available_at_utc,
    'open_meteo_era5' AS label_source,
    'heat,rain' AS supported_target_components,
    'wind,air,river' AS unsupported_target_components,
    'latest_complete_weather_vintage_per_city_local_origin_date'
        AS canonical_vintage_rule
FROM labels_joined
