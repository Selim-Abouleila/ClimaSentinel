{{ config(
    materialized='table',
    partition_by={
      "field": "date",
      "data_type": "date",
      "granularity": "day"
    }
) }}

WITH daily_signals AS (
    SELECT
        signals.*,
        EXTRACT(MONTH FROM signals.date) AS month
    FROM {{ ref('stg_city_signal_input_v2') }} AS signals
),

signals_with_baselines AS (
    SELECT
        signals.*,
        normals.normal_temperature_2m_max
    FROM daily_signals AS signals
    LEFT JOIN {{ ref('city_monthly_normals') }} AS normals
        ON signals.city_id = normals.city_id
        AND signals.month = normals.month
),

signals_with_leads AS (
    SELECT
        *,
        LEAD(date) OVER (
            PARTITION BY city_id ORDER BY date
        ) AS next_date,
        LEAD(temperature_2m_max) OVER (
            PARTITION BY city_id ORDER BY date
        ) AS next_temperature_2m_max,
        LEAD(temperature_2m_value_count) OVER (
            PARTITION BY city_id ORDER BY date
        ) AS next_temperature_2m_value_count,
        LEAD(river_discharge_m3s) OVER (
            PARTITION BY city_id ORDER BY date
        ) AS next_river_discharge_m3s
    FROM signals_with_baselines
),

signals_with_velocity AS (
    SELECT
        *,

        -- A velocity is unavailable unless both daily values were observed.
        CASE
            WHEN temperature_2m_max IS NOT NULL
                AND next_temperature_2m_max IS NOT NULL
                AND next_date = DATE_ADD(date, INTERVAL 1 DAY)
                THEN next_temperature_2m_max - temperature_2m_max
        END AS temp_velocity,

        -- A low measured discharge is a valid zero-risk observation. Above
        -- the activation threshold, both consecutive days are required to
        -- calculate velocity; a missing next day must remain unavailable.
        CASE
            WHEN NOT river_monitored OR river_discharge_m3s IS NULL THEN NULL
            -- Below the activation threshold the current observation is
            -- sufficient for the documented zero score; velocity is unused.
            WHEN river_discharge_m3s <= 50 THEN 0
            WHEN next_date != DATE_ADD(date, INTERVAL 1 DAY) THEN NULL
            WHEN next_river_discharge_m3s IS NULL THEN NULL
            ELSE (
                next_river_discharge_m3s - river_discharge_m3s
            ) / river_discharge_m3s
        END AS river_velocity_pct
    FROM signals_with_leads
),

factor_scores AS (
    SELECT
        *,

        -- Heat requires the current and next temperature plus the monthly
        -- baseline because both anomaly and velocity are score inputs.
        CASE
            WHEN heat_monitored
                AND temperature_2m_max IS NOT NULL
                AND normal_temperature_2m_max IS NOT NULL
                AND temp_velocity IS NOT NULL
                AND temperature_2m_value_count = 24
                AND next_temperature_2m_value_count = 24
                THEN GREATEST(
                    0,
                    LEAST(
                        100,
                        ((temperature_2m_max - normal_temperature_2m_max) * 5)
                        + (GREATEST(0, temp_velocity) * 5)
                    )
                )
        END AS heat_score,

        CASE
            WHEN wind_monitored
                AND wind_gusts_10m_max IS NOT NULL
                AND wind_gusts_10m_value_count = 24
                THEN GREATEST(
                    0,
                    LEAST(100, GREATEST(0, wind_gusts_10m_max - 40) * 2.5)
                )
        END AS wind_score,

        CASE
            WHEN rain_monitored
                AND precipitation_sum_mm IS NOT NULL
                AND precipitation_value_count = 24
                THEN GREATEST(0, LEAST(100, precipitation_sum_mm * 2))
        END AS rain_score,

        -- No zero default and no carry-forward: an AQ gap remains an AQ gap.
        CASE
            WHEN air_monitored
                AND european_aqi_max IS NOT NULL
                AND european_aqi_value_count = 24
                THEN GREATEST(
                    0,
                    LEAST(100, (european_aqi_max - 40) * 1.67)
                )
        END AS air_score,

        CASE
            WHEN river_monitored AND river_velocity_pct IS NOT NULL
                THEN GREATEST(
                    0,
                    LEAST(100, GREATEST(0, river_velocity_pct) * 200)
                )
        END AS river_score

    FROM signals_with_velocity
),

scores_with_metadata AS (
    SELECT
        *,

        heat_score IS NOT NULL AS heat_available,
        wind_score IS NOT NULL AS wind_available,
        rain_score IS NOT NULL AS rain_available,
        air_score IS NOT NULL AS air_available,
        river_score IS NOT NULL AS river_available,

        CASE
            WHEN NOT heat_monitored THEN 'not_monitored'
            WHEN heat_score IS NULL THEN 'unavailable'
            ELSE 'available'
        END AS heat_status,
        CASE
            WHEN NOT wind_monitored THEN 'not_monitored'
            WHEN wind_score IS NULL THEN 'unavailable'
            ELSE 'available'
        END AS wind_status,
        CASE
            WHEN NOT rain_monitored THEN 'not_monitored'
            WHEN rain_score IS NULL THEN 'unavailable'
            ELSE 'available'
        END AS rain_status,
        CASE
            WHEN NOT air_monitored THEN 'not_monitored'
            WHEN air_score IS NULL THEN 'unavailable'
            ELSE 'available'
        END AS air_status,
        CASE
            WHEN NOT river_monitored THEN 'not_monitored'
            WHEN river_score IS NULL THEN 'unavailable'
            ELSE 'available'
        END AS river_status,

        CASE
            WHEN NOT heat_monitored THEN NULL
            ELSE LEAST(
                1.0,
                COALESCE(SAFE_DIVIDE(temperature_2m_value_count, 24), 0.0),
                IF(
                    next_date = DATE_ADD(date, INTERVAL 1 DAY),
                    COALESCE(
                        SAFE_DIVIDE(next_temperature_2m_value_count, 24),
                        0.0
                    ),
                    0.0
                ),
                IF(normal_temperature_2m_max IS NOT NULL, 1.0, 0.0)
            )
        END AS heat_coverage,
        CASE
            WHEN NOT wind_monitored THEN NULL
            ELSE LEAST(
                1.0,
                COALESCE(SAFE_DIVIDE(wind_gusts_10m_value_count, 24), 0.0)
            )
        END AS wind_coverage,
        CASE
            WHEN NOT rain_monitored THEN NULL
            ELSE LEAST(
                1.0,
                COALESCE(SAFE_DIVIDE(precipitation_value_count, 24), 0.0)
            )
        END AS rain_coverage,
        CASE
            WHEN NOT air_monitored THEN NULL
            ELSE LEAST(
                1.0,
                COALESCE(SAFE_DIVIDE(european_aqi_value_count, 24), 0.0)
            )
        END AS air_coverage,
        CASE
            WHEN NOT river_monitored THEN NULL
            WHEN river_discharge_m3s IS NULL THEN 0.0
            WHEN river_discharge_m3s <= 50 THEN 1.0
            ELSE (
                1.0
                + IF(
                    next_date = DATE_ADD(date, INTERVAL 1 DAY)
                    AND next_river_discharge_m3s IS NOT NULL,
                    1.0,
                    0.0
                )
            ) / 2.0
        END AS river_coverage

    FROM factor_scores
),

scores_with_global AS (
    SELECT
        *,
        (
            SELECT MAX(score)
            FROM UNNEST([
                heat_score,
                wind_score,
                rain_score,
                air_score,
                river_score
            ]) AS score
        ) AS global_tipping_score,
        (
            IF(heat_monitored, 1, 0)
            + IF(wind_monitored, 1, 0)
            + IF(rain_monitored, 1, 0)
            + IF(air_monitored, 1, 0)
            + IF(river_monitored, 1, 0)
        ) AS monitored_factor_count,
        (
            IF(heat_available, 1, 0)
            + IF(wind_available, 1, 0)
            + IF(rain_available, 1, 0)
            + IF(air_available, 1, 0)
            + IF(river_available, 1, 0)
        ) AS available_factor_count
    FROM scores_with_metadata
),

final_scores AS (
    SELECT
        operational_ingestion_run_id,
        operational_ingested_at_utc,
        run_has_weather_source,
        run_has_air_quality_source,
        run_has_flood_source,
        run_has_historical_weather_source,
        run_source_count,
        city_id,
        date,

        weather_source_available,
        weather_ingested_at_utc,
        air_quality_source_available,
        air_quality_ingested_at_utc,
        flood_source_available,
        flood_ingested_at_utc,

        -- Raw values for context.
        temperature_2m_max,
        precipitation_sum_mm,
        wind_gusts_10m_max,
        european_aqi_max,
        river_discharge_m3s,

        -- Nullable factor scores: NULL means no defensible score exists.
        ROUND(heat_score, 1) AS heat_score,
        ROUND(wind_score, 1) AS wind_score,
        ROUND(rain_score, 1) AS rain_score,
        ROUND(air_score, 1) AS air_score,
        ROUND(river_score, 1) AS river_score,

        heat_status,
        heat_monitored,
        heat_available,
        ROUND(heat_coverage, 3) AS heat_coverage,
        wind_status,
        wind_monitored,
        wind_available,
        ROUND(wind_coverage, 3) AS wind_coverage,
        rain_status,
        rain_monitored,
        rain_available,
        ROUND(rain_coverage, 3) AS rain_coverage,
        air_status,
        air_monitored,
        air_available,
        ROUND(air_coverage, 3) AS air_coverage,
        river_status,
        river_monitored,
        river_available,
        ROUND(river_coverage, 3) AS river_coverage,

        monitored_factor_count,
        available_factor_count,
        ROUND(
            SAFE_DIVIDE(
                COALESCE(heat_coverage, 0.0)
                + COALESCE(wind_coverage, 0.0)
                + COALESCE(rain_coverage, 0.0)
                + COALESCE(air_coverage, 0.0)
                + COALESCE(river_coverage, 0.0),
                monitored_factor_count
            ),
            3
        ) AS overall_coverage,
        global_tipping_score IS NOT NULL AS global_score_available,
        ROUND(global_tipping_score, 1) AS global_tipping_score,

        CASE
            WHEN global_tipping_score IS NULL THEN 'Unavailable'
            WHEN global_tipping_score = 0 THEN 'Stable'
            WHEN global_tipping_score = heat_score THEN 'Heat'
            WHEN global_tipping_score = river_score THEN 'River/Flood'
            WHEN global_tipping_score = wind_score THEN 'Wind'
            WHEN global_tipping_score = rain_score THEN 'Rain'
            WHEN global_tipping_score = air_score THEN 'Air Quality'
            ELSE 'Unknown'
        END AS primary_driver

    FROM scores_with_global
)

SELECT *
FROM final_scores
