{{ config(tags=['ml_point_in_time']) }}

-- Only ERA5-backed Heat and Rain may become mature labels. Unsupported Wind,
-- Air and River targets must remain explicitly absent rather than being filled
-- from forecasts or later forecast revisions.

WITH realized_with_lineage AS (
    SELECT
        realized.*,
        source.city_id AS source_city_id,
        source.temperature_2m_mean AS source_temperature_2m_mean,
        source.temperature_2m_max AS source_temperature_2m_max,
        source.temperature_2m_min AS source_temperature_2m_min,
        source.precipitation_sum_mm AS source_precipitation_sum_mm,
        source.wind_speed_10m_max AS source_wind_speed_10m_max,
        source.ingestion_run_id AS source_ingestion_run_id,
        source.ingested_at_utc AS source_ingested_at_utc,
        next_day.temperature_2m_max AS source_next_day_temperature_2m_max,
        next_day.ingestion_run_id AS source_next_day_ingestion_run_id,
        next_day.ingested_at_utc AS source_next_day_ingested_at_utc,
        normals.normal_temperature_2m_max AS source_normal_temperature_2m_max
    FROM {{ ref('mart_city_realized_weather_daily') }} realized
    LEFT JOIN {{ ref('stg_latest_historical_daily') }} source
        ON realized.city_id = source.city_id
        AND realized.valid_date = source.date
    LEFT JOIN {{ ref('stg_latest_historical_daily') }} next_day
        ON realized.city_id = next_day.city_id
        AND next_day.date = DATE_ADD(realized.valid_date, INTERVAL 1 DAY)
    LEFT JOIN {{ ref('city_monthly_normals') }} normals
        ON realized.city_id = normals.city_id
        AND EXTRACT(MONTH FROM realized.valid_date) = normals.month
)

SELECT
    city_id,
    valid_date,
    label_source,
    unsupported_label_components
FROM realized_with_lineage
WHERE source_city_id IS NULL
    OR realized_temperature_2m_mean IS DISTINCT FROM source_temperature_2m_mean
    OR realized_temperature_2m_max IS DISTINCT FROM source_temperature_2m_max
    OR realized_temperature_2m_min IS DISTINCT FROM source_temperature_2m_min
    OR realized_precipitation_sum_mm IS DISTINCT FROM source_precipitation_sum_mm
    OR realized_wind_speed_10m_max IS DISTINCT FROM source_wind_speed_10m_max
    OR realized_weather_ingestion_run_id IS DISTINCT FROM source_ingestion_run_id
    OR realized_weather_ingested_at_utc IS DISTINCT FROM source_ingested_at_utc
    OR next_day_temperature_2m_max
        IS DISTINCT FROM source_next_day_temperature_2m_max
    OR next_day_weather_ingestion_run_id
        IS DISTINCT FROM source_next_day_ingestion_run_id
    OR next_day_weather_ingested_at_utc
        IS DISTINCT FROM source_next_day_ingested_at_utc
    OR normal_temperature_2m_max IS DISTINCT FROM source_normal_temperature_2m_max
    OR has_realized_heat_label IS DISTINCT FROM (realized_heat_score IS NOT NULL)
    OR has_realized_rain_label IS DISTINCT FROM (realized_rain_score IS NOT NULL)
    OR has_mature_realized_labels IS DISTINCT FROM (
        realized_heat_score IS NOT NULL
        AND realized_rain_score IS NOT NULL
    )
    OR has_realized_wind_label
    OR has_realized_air_label
    OR has_realized_river_label
    OR realized_wind_score IS NOT NULL
    OR realized_air_score IS NOT NULL
    OR realized_river_score IS NOT NULL
    OR label_source != 'open_meteo_era5'
    OR unsupported_label_components != 'wind,air,river'
    OR realized_heat_score < 0
    OR realized_heat_score > 100
    OR realized_rain_score < 0
    OR realized_rain_score > 100
    OR realized_heat_score IS DISTINCT FROM (
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
                            realized_temperature_2m_max
                            - normal_temperature_2m_max
                        ) * 5
                        + GREATEST(
                            0,
                            next_day_temperature_2m_max
                            - realized_temperature_2m_max
                        ) * 5
                    )
                ),
                1
            )
        END
    )
    OR realized_rain_score IS DISTINCT FROM (
        CASE
            WHEN realized_precipitation_sum_mm IS NOT NULL
            THEN ROUND(
                GREATEST(
                    0,
                    LEAST(100, realized_precipitation_sum_mm * 2)
                ),
                1
            )
        END
    )
    OR realized_temperature_velocity IS DISTINCT FROM (
        next_day_temperature_2m_max - realized_temperature_2m_max
    )
    OR heat_label_available_at_utc IS DISTINCT FROM (
        CASE
            WHEN realized_heat_score IS NOT NULL
            THEN GREATEST(
                realized_weather_ingested_at_utc,
                next_day_weather_ingested_at_utc
            )
        END
    )
    OR rain_label_available_at_utc IS DISTINCT FROM (
        CASE
            WHEN realized_rain_score IS NOT NULL
            THEN realized_weather_ingested_at_utc
        END
    )
    OR labels_available_at_utc IS DISTINCT FROM (
        CASE
            WHEN realized_heat_score IS NOT NULL
                AND realized_rain_score IS NOT NULL
            THEN GREATEST(
                realized_weather_ingested_at_utc,
                next_day_weather_ingested_at_utc
            )
        END
    )
