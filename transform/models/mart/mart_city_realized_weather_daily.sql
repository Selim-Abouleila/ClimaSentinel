{{ config(
    materialized='table',
    partition_by={
      "field": "valid_date",
      "data_type": "date",
      "granularity": "day"
    },
    cluster_by=['city_id'],
    tags=['ml_point_in_time']
) }}

-- Honest realized labels backed only by ERA5 reanalysis.
--
-- Grain: one row per (city_id, valid_date).
--
-- Heat uses the same documented scoring rule as the operational score: the
-- day's temperature anomaly plus only positive movement into the following
-- day. Consequently, a heat label is not mature until ERA5 has published both
-- valid_date and valid_date + 1. Rain needs only the current ERA5 day.
--
-- ERA5 currently does not provide the gust, observed AQ, or observed river
-- fields needed for honest wind, air, and river labels. Those scores remain
-- explicitly NULL; forecast values are never substituted as realized truth.

WITH realized_weather AS (
    SELECT
        h.city_id,
        h.date AS valid_date,
        h.temperature_2m_mean AS realized_temperature_2m_mean,
        h.temperature_2m_max AS realized_temperature_2m_max,
        h.temperature_2m_min AS realized_temperature_2m_min,
        h.precipitation_sum_mm AS realized_precipitation_sum_mm,
        h.wind_speed_10m_max AS realized_wind_speed_10m_max,
        h.ingestion_run_id AS realized_weather_ingestion_run_id,
        h.ingested_at_utc AS realized_weather_ingested_at_utc,

        next_day.temperature_2m_max AS next_day_temperature_2m_max,
        next_day.ingestion_run_id AS next_day_weather_ingestion_run_id,
        next_day.ingested_at_utc AS next_day_weather_ingested_at_utc,

        normals.normal_temperature_2m_max
    FROM {{ ref('stg_latest_historical_daily') }} h
    LEFT JOIN {{ ref('stg_latest_historical_daily') }} next_day
        ON h.city_id = next_day.city_id
        AND next_day.date = DATE_ADD(h.date, INTERVAL 1 DAY)
    LEFT JOIN {{ ref('city_monthly_normals') }} normals
        ON h.city_id = normals.city_id
        AND EXTRACT(MONTH FROM h.date) = normals.month
),

scored AS (
    SELECT
        *,
        next_day_temperature_2m_max - realized_temperature_2m_max
            AS realized_temperature_velocity,

        CASE
            WHEN realized_temperature_2m_max IS NOT NULL
                AND next_day_temperature_2m_max IS NOT NULL
                AND normal_temperature_2m_max IS NOT NULL
            THEN ROUND(
                GREATEST(
                    0,
                    LEAST(
                        100,
                        (
                            (realized_temperature_2m_max - normal_temperature_2m_max) * 5
                        ) + (
                            GREATEST(
                                0,
                                next_day_temperature_2m_max - realized_temperature_2m_max
                            ) * 5
                        )
                    )
                ),
                1
            )
        END AS realized_heat_score,

        CASE
            WHEN realized_precipitation_sum_mm IS NOT NULL
            THEN ROUND(
                GREATEST(
                    0,
                    LEAST(100, realized_precipitation_sum_mm * 2)
                ),
                1
            )
        END AS realized_rain_score
    FROM realized_weather
)

SELECT
    city_id,
    valid_date,

    realized_temperature_2m_mean,
    realized_temperature_2m_max,
    realized_temperature_2m_min,
    realized_precipitation_sum_mm,
    realized_wind_speed_10m_max,
    normal_temperature_2m_max,
    next_day_temperature_2m_max,
    realized_temperature_velocity,

    realized_heat_score,
    realized_rain_score,
    CAST(NULL AS FLOAT64) AS realized_wind_score,
    CAST(NULL AS FLOAT64) AS realized_air_score,
    CAST(NULL AS FLOAT64) AS realized_river_score,

    realized_heat_score IS NOT NULL AS has_realized_heat_label,
    realized_rain_score IS NOT NULL AS has_realized_rain_label,
    FALSE AS has_realized_wind_label,
    FALSE AS has_realized_air_label,
    FALSE AS has_realized_river_label,
    realized_heat_score IS NOT NULL
        AND realized_rain_score IS NOT NULL AS has_mature_realized_labels,

    realized_weather_ingestion_run_id,
    realized_weather_ingested_at_utc,
    next_day_weather_ingestion_run_id,
    next_day_weather_ingested_at_utc,
    CASE
        WHEN realized_heat_score IS NOT NULL
        THEN GREATEST(
            realized_weather_ingested_at_utc,
            next_day_weather_ingested_at_utc
        )
    END AS heat_label_available_at_utc,
    CASE
        WHEN realized_rain_score IS NOT NULL
        THEN realized_weather_ingested_at_utc
    END AS rain_label_available_at_utc,
    CASE
        WHEN realized_heat_score IS NOT NULL
            AND realized_rain_score IS NOT NULL
        THEN GREATEST(
            realized_weather_ingested_at_utc,
            next_day_weather_ingested_at_utc
        )
    END AS labels_available_at_utc,

    'open_meteo_era5' AS label_source,
    'wind,air,river' AS unsupported_label_components
FROM scored
