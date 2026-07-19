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

-- Point-in-time-safe forecast features shared by model training and serving.
--
-- Grain: one row per (ingestion_run_id, city_id, forecast_origin_date).
-- Every horizon is pivoted from the same source snapshot; no LEAD across runs
-- or fallback to a later vintage is allowed. AQ and flood remain nullable and
-- have explicit presence/coverage flags so absence is not confused with zero.

WITH horizon_pivot AS (
    SELECT
        ingestion_run_id,
        city_id,
        forecast_origin_date,
        MIN(ingested_at_utc) AS ingested_at_utc,
        ANY_VALUE(forecast_origin_time_zone) AS forecast_origin_time_zone,

        -- Dates prove that each feature belongs to the expected local horizon.
        MAX(IF(horizon_days = 0, valid_date, NULL)) AS valid_date_0d,
        MAX(IF(horizon_days = 1, valid_date, NULL)) AS valid_date_plus_1d,
        MAX(IF(horizon_days = 2, valid_date, NULL)) AS valid_date_plus_2d,
        MAX(IF(horizon_days = 3, valid_date, NULL)) AS valid_date_plus_3d,
        MAX(IF(horizon_days = 4, valid_date, NULL)) AS valid_date_plus_4d,

        -- Current (horizon-zero) feature values.
        MAX(IF(horizon_days = 0, temperature_2m_max, NULL)) AS temperature_2m_max,
        MAX(IF(horizon_days = 0, temperature_2m_min, NULL)) AS temperature_2m_min,
        MAX(IF(horizon_days = 0, precipitation_sum_mm, NULL)) AS precipitation_sum_mm,
        MAX(IF(horizon_days = 0, wind_speed_10m_max, NULL)) AS wind_speed_10m_max,
        MAX(IF(horizon_days = 0, wind_gusts_10m_max, NULL)) AS wind_gusts_10m_max,
        MAX(IF(horizon_days = 0, european_aqi_max, NULL)) AS european_aqi_max,
        MAX(IF(horizon_days = 0, river_discharge_m3s, NULL)) AS river_discharge_m3s,

        -- Future values use the legacy FEATURE_COLUMNS names so the eventual
        -- Python cutover can share one feature contract with minimal churn.
        MAX(IF(horizon_days = 1, temperature_2m_max, NULL)) AS temp_forecast_plus_1d,
        MAX(IF(horizon_days = 2, temperature_2m_max, NULL)) AS temp_forecast_plus_2d,
        MAX(IF(horizon_days = 3, temperature_2m_max, NULL)) AS temp_forecast_plus_3d,
        MAX(IF(horizon_days = 4, temperature_2m_max, NULL)) AS temp_forecast_plus_4d,

        MAX(IF(horizon_days = 1, precipitation_sum_mm, NULL)) AS precip_forecast_plus_1d,
        MAX(IF(horizon_days = 2, precipitation_sum_mm, NULL)) AS precip_forecast_plus_2d,
        MAX(IF(horizon_days = 3, precipitation_sum_mm, NULL)) AS precip_forecast_plus_3d,

        MAX(IF(horizon_days = 1, wind_speed_10m_max, NULL)) AS wind_forecast_plus_1d,
        MAX(IF(horizon_days = 2, wind_speed_10m_max, NULL)) AS wind_forecast_plus_2d,
        MAX(IF(horizon_days = 3, wind_speed_10m_max, NULL)) AS wind_forecast_plus_3d,

        MAX(IF(horizon_days = 1, wind_gusts_10m_max, NULL)) AS wind_gusts_forecast_plus_1d,
        MAX(IF(horizon_days = 2, wind_gusts_10m_max, NULL)) AS wind_gusts_forecast_plus_2d,
        MAX(IF(horizon_days = 3, wind_gusts_10m_max, NULL)) AS wind_gusts_forecast_plus_3d,

        MAX(IF(horizon_days = 1, european_aqi_max, NULL)) AS aqi_forecast_plus_1d,
        MAX(IF(horizon_days = 2, european_aqi_max, NULL)) AS aqi_forecast_plus_2d,
        MAX(IF(horizon_days = 3, european_aqi_max, NULL)) AS aqi_forecast_plus_3d,

        MAX(IF(horizon_days = 1, river_discharge_m3s, NULL)) AS river_forecast_plus_1d,
        MAX(IF(horizon_days = 2, river_discharge_m3s, NULL)) AS river_forecast_plus_2d,
        MAX(IF(horizon_days = 3, river_discharge_m3s, NULL)) AS river_forecast_plus_3d,
        MAX(IF(horizon_days = 4, river_discharge_m3s, NULL)) AS river_forecast_plus_4d,

        -- Required weather horizon/coverage contract.
        COUNTIF(horizon_days = 0) > 0 AS has_horizon_0d,
        COUNTIF(horizon_days = 1) > 0 AS has_horizon_plus_1d,
        COUNTIF(horizon_days = 2) > 0 AS has_horizon_plus_2d,
        COUNTIF(horizon_days = 3) > 0 AS has_horizon_plus_3d,
        COUNTIF(horizon_days = 4) > 0 AS has_horizon_plus_4d,

        COUNTIF(horizon_days = 0 AND COALESCE(weather_has_24_hour_coverage, FALSE)) > 0
            AS weather_has_24_hour_coverage_0d,
        COUNTIF(horizon_days = 1 AND COALESCE(weather_has_24_hour_coverage, FALSE)) > 0
            AS weather_has_24_hour_coverage_plus_1d,
        COUNTIF(horizon_days = 2 AND COALESCE(weather_has_24_hour_coverage, FALSE)) > 0
            AS weather_has_24_hour_coverage_plus_2d,
        COUNTIF(horizon_days = 3 AND COALESCE(weather_has_24_hour_coverage, FALSE)) > 0
            AS weather_has_24_hour_coverage_plus_3d,
        COUNTIF(horizon_days = 4 AND COALESCE(weather_has_24_hour_coverage, FALSE)) > 0
            AS weather_has_24_hour_coverage_plus_4d,

        COUNTIF(horizon_days = 0 AND COALESCE(has_complete_weather_values, FALSE)) > 0
            AS has_complete_weather_values_0d,
        COUNTIF(horizon_days = 1 AND COALESCE(has_complete_weather_values, FALSE)) > 0
            AS has_complete_weather_values_plus_1d,
        COUNTIF(horizon_days = 2 AND COALESCE(has_complete_weather_values, FALSE)) > 0
            AS has_complete_weather_values_plus_2d,
        COUNTIF(horizon_days = 3 AND COALESCE(has_complete_weather_values, FALSE)) > 0
            AS has_complete_weather_values_plus_3d,
        COUNTIF(horizon_days = 4 AND COALESCE(has_complete_weather_values, FALSE)) > 0
            AS has_complete_weather_values_plus_4d,

        -- AQ is optional, but source presence, daily coverage, and value
        -- completeness are kept separate for every horizon.
        COUNTIF(horizon_days = 0 AND COALESCE(has_air_quality_forecast, FALSE)) > 0
            AS has_air_quality_forecast_0d,
        COUNTIF(horizon_days = 1 AND COALESCE(has_air_quality_forecast, FALSE)) > 0
            AS has_air_quality_forecast_plus_1d,
        COUNTIF(horizon_days = 2 AND COALESCE(has_air_quality_forecast, FALSE)) > 0
            AS has_air_quality_forecast_plus_2d,
        COUNTIF(horizon_days = 3 AND COALESCE(has_air_quality_forecast, FALSE)) > 0
            AS has_air_quality_forecast_plus_3d,
        COUNTIF(horizon_days = 4 AND COALESCE(has_air_quality_forecast, FALSE)) > 0
            AS has_air_quality_forecast_plus_4d,

        COUNTIF(horizon_days = 0 AND COALESCE(air_quality_has_24_hour_coverage, FALSE)) > 0
            AS air_quality_has_24_hour_coverage_0d,
        COUNTIF(horizon_days = 1 AND COALESCE(air_quality_has_24_hour_coverage, FALSE)) > 0
            AS air_quality_has_24_hour_coverage_plus_1d,
        COUNTIF(horizon_days = 2 AND COALESCE(air_quality_has_24_hour_coverage, FALSE)) > 0
            AS air_quality_has_24_hour_coverage_plus_2d,
        COUNTIF(horizon_days = 3 AND COALESCE(air_quality_has_24_hour_coverage, FALSE)) > 0
            AS air_quality_has_24_hour_coverage_plus_3d,
        COUNTIF(horizon_days = 4 AND COALESCE(air_quality_has_24_hour_coverage, FALSE)) > 0
            AS air_quality_has_24_hour_coverage_plus_4d,

        COUNTIF(horizon_days = 0 AND COALESCE(has_complete_air_quality_values, FALSE)) > 0
            AS has_complete_air_quality_values_0d,
        COUNTIF(horizon_days = 1 AND COALESCE(has_complete_air_quality_values, FALSE)) > 0
            AS has_complete_air_quality_values_plus_1d,
        COUNTIF(horizon_days = 2 AND COALESCE(has_complete_air_quality_values, FALSE)) > 0
            AS has_complete_air_quality_values_plus_2d,
        COUNTIF(horizon_days = 3 AND COALESCE(has_complete_air_quality_values, FALSE)) > 0
            AS has_complete_air_quality_values_plus_3d,
        COUNTIF(horizon_days = 4 AND COALESCE(has_complete_air_quality_values, FALSE)) > 0
            AS has_complete_air_quality_values_plus_4d,

        -- Flood is optional and expected only for river-enabled cities.
        COUNTIF(horizon_days = 0 AND COALESCE(has_flood_forecast, FALSE)) > 0
            AS has_flood_forecast_0d,
        COUNTIF(horizon_days = 1 AND COALESCE(has_flood_forecast, FALSE)) > 0
            AS has_flood_forecast_plus_1d,
        COUNTIF(horizon_days = 2 AND COALESCE(has_flood_forecast, FALSE)) > 0
            AS has_flood_forecast_plus_2d,
        COUNTIF(horizon_days = 3 AND COALESCE(has_flood_forecast, FALSE)) > 0
            AS has_flood_forecast_plus_3d,
        COUNTIF(horizon_days = 4 AND COALESCE(has_flood_forecast, FALSE)) > 0
            AS has_flood_forecast_plus_4d

    FROM {{ ref('stg_city_signal_vintage') }}
    WHERE horizon_days BETWEEN 0 AND 4
    GROUP BY
        ingestion_run_id,
        city_id,
        forecast_origin_date
),

features_with_normals AS (
    SELECT
        p.*,
        n.normal_temperature_2m_max
    FROM horizon_pivot p
    LEFT JOIN {{ ref('city_monthly_normals') }} n
        ON p.city_id = n.city_id
        AND EXTRACT(MONTH FROM p.forecast_origin_date) = n.month
),

factor_scores AS (
    SELECT
        f.*,

        -- Same-vintage h0 baseline. Heat/river velocity uses only h1 from
        -- this run. Missing optional AQ/flood contributes zero, matching the
        -- existing score semantics without borrowing data from another run.
        GREATEST(
            0,
            LEAST(
                100,
                ((temperature_2m_max - normal_temperature_2m_max) * 5)
                + (
                    GREATEST(
                        0,
                        COALESCE(temp_forecast_plus_1d - temperature_2m_max, 0)
                    ) * 5
                )
            )
        ) AS _current_heat_score,

        GREATEST(
            0,
            LEAST(100, GREATEST(0, wind_gusts_10m_max - 40) * 2.5)
        ) AS _current_wind_score,

        GREATEST(0, LEAST(100, precipitation_sum_mm * 2))
            AS _current_rain_score,

        GREATEST(
            0,
            LEAST(100, (COALESCE(european_aqi_max, 0) - 40) * 1.67)
        ) AS _current_air_score,

        GREATEST(
            0,
            LEAST(
                100,
                GREATEST(
                    0,
                    CASE
                        WHEN river_discharge_m3s IS NOT NULL
                            AND river_discharge_m3s > 50
                        THEN COALESCE(
                            (
                                river_forecast_plus_1d
                                - river_discharge_m3s
                            ) / river_discharge_m3s,
                            0
                        )
                        ELSE 0
                    END
                ) * 200
            )
        ) AS _current_river_score

    FROM features_with_normals f
),

scored_and_validated AS (
    SELECT
        * EXCEPT (
            _current_heat_score,
            _current_wind_score,
            _current_rain_score,
            _current_air_score,
            _current_river_score
        ),

        ROUND(
            GREATEST(
                _current_heat_score,
                _current_wind_score,
                _current_rain_score,
                _current_air_score,
                _current_river_score
            ),
            1
        ) AS current_tipping_score,

        COALESCE(
            valid_date_0d = forecast_origin_date
            AND valid_date_plus_1d = DATE_ADD(forecast_origin_date, INTERVAL 1 DAY)
            AND valid_date_plus_2d = DATE_ADD(forecast_origin_date, INTERVAL 2 DAY)
            AND valid_date_plus_3d = DATE_ADD(forecast_origin_date, INTERVAL 3 DAY)
            AND valid_date_plus_4d = DATE_ADD(forecast_origin_date, INTERVAL 4 DAY),
            FALSE
        ) AS has_expected_horizon_dates,

        COALESCE(
            has_horizon_0d
            AND has_horizon_plus_1d
            AND has_horizon_plus_2d
            AND has_horizon_plus_3d
            AND has_horizon_plus_4d
            AND weather_has_24_hour_coverage_0d
            AND weather_has_24_hour_coverage_plus_1d
            AND weather_has_24_hour_coverage_plus_2d
            AND weather_has_24_hour_coverage_plus_3d
            AND weather_has_24_hour_coverage_plus_4d
            AND has_complete_weather_values_0d
            AND has_complete_weather_values_plus_1d
            AND has_complete_weather_values_plus_2d
            AND has_complete_weather_values_plus_3d
            AND has_complete_weather_values_plus_4d
            AND valid_date_0d = forecast_origin_date
            AND valid_date_plus_1d = DATE_ADD(forecast_origin_date, INTERVAL 1 DAY)
            AND valid_date_plus_2d = DATE_ADD(forecast_origin_date, INTERVAL 2 DAY)
            AND valid_date_plus_3d = DATE_ADD(forecast_origin_date, INTERVAL 3 DAY)
            AND valid_date_plus_4d = DATE_ADD(forecast_origin_date, INTERVAL 4 DAY),
            FALSE
        ) AS has_complete_weather_feature_window

    FROM factor_scores
),

ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY city_id, forecast_origin_date
            ORDER BY
                CASE WHEN has_complete_weather_feature_window THEN 0 ELSE 1 END,
                ingested_at_utc DESC,
                ingestion_run_id DESC
        ) AS _daily_vintage_rank
    FROM scored_and_validated
)

SELECT
    * EXCEPT (_daily_vintage_rank),
    has_complete_weather_feature_window
        AND _daily_vintage_rank = 1 AS is_canonical_daily_vintage
FROM ranked
