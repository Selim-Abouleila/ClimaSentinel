{{ config(tags=['ml_point_in_time']) }}

-- A feature row may preserve an incomplete vintage, but its dates and flags
-- must describe that vintage truthfully. Exactly one latest complete vintage
-- is canonical when a city/origin date has at least one eligible candidate.

WITH features AS (
    SELECT
        *,
        COALESCE(
            valid_date_0d = forecast_origin_date
            AND valid_date_plus_1d = DATE_ADD(forecast_origin_date, INTERVAL 1 DAY)
            AND valid_date_plus_2d = DATE_ADD(forecast_origin_date, INTERVAL 2 DAY)
            AND valid_date_plus_3d = DATE_ADD(forecast_origin_date, INTERVAL 3 DAY)
            AND valid_date_plus_4d = DATE_ADD(forecast_origin_date, INTERVAL 4 DAY),
            FALSE
        ) AS expected_horizon_dates_from_payload,
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
        ) AS complete_weather_window_from_payload
    FROM {{ ref('mart_ml_forecast_features_vintage') }}
),

row_violations AS (
    SELECT
        'row_contract' AS violation_type,
        CAST(ingestion_run_id AS STRING) AS ingestion_run_id,
        city_id,
        forecast_origin_date
    FROM features
    WHERE forecast_origin_date IS DISTINCT FROM DATE(
            ingested_at_utc,
            forecast_origin_time_zone
        )
        OR has_horizon_0d IS DISTINCT FROM (valid_date_0d IS NOT NULL)
        OR has_horizon_plus_1d IS DISTINCT FROM (valid_date_plus_1d IS NOT NULL)
        OR has_horizon_plus_2d IS DISTINCT FROM (valid_date_plus_2d IS NOT NULL)
        OR has_horizon_plus_3d IS DISTINCT FROM (valid_date_plus_3d IS NOT NULL)
        OR has_horizon_plus_4d IS DISTINCT FROM (valid_date_plus_4d IS NOT NULL)
        OR has_expected_horizon_dates IS DISTINCT FROM expected_horizon_dates_from_payload
        OR has_complete_weather_feature_window
            IS DISTINCT FROM complete_weather_window_from_payload
        OR (
            is_canonical_daily_vintage
            AND NOT has_complete_weather_feature_window
        )
        OR (
            has_complete_weather_feature_window
            AND (
                normal_temperature_2m_max IS NULL
                OR current_tipping_score IS NULL
                OR temperature_2m_max IS NULL
                OR temperature_2m_min IS NULL
                OR precipitation_sum_mm IS NULL
                OR wind_speed_10m_max IS NULL
                OR wind_gusts_10m_max IS NULL
                OR temp_forecast_plus_1d IS NULL
                OR temp_forecast_plus_2d IS NULL
                OR temp_forecast_plus_3d IS NULL
                OR temp_forecast_plus_4d IS NULL
                OR precip_forecast_plus_1d IS NULL
                OR precip_forecast_plus_2d IS NULL
                OR precip_forecast_plus_3d IS NULL
                OR wind_forecast_plus_1d IS NULL
                OR wind_forecast_plus_2d IS NULL
                OR wind_forecast_plus_3d IS NULL
                OR wind_gusts_forecast_plus_1d IS NULL
                OR wind_gusts_forecast_plus_2d IS NULL
                OR wind_gusts_forecast_plus_3d IS NULL
            )
        )
),

canonical_group_violations AS (
    SELECT
        'canonical_count' AS violation_type,
        CAST(NULL AS STRING) AS ingestion_run_id,
        city_id,
        forecast_origin_date
    FROM features
    GROUP BY city_id, forecast_origin_date
    HAVING COUNTIF(is_canonical_daily_vintage) != IF(
        COUNTIF(has_complete_weather_feature_window) > 0,
        1,
        0
    )
),

canonical_order_violations AS (
    SELECT
        'canonical_not_latest' AS violation_type,
        CAST(c.ingestion_run_id AS STRING) AS ingestion_run_id,
        c.city_id,
        c.forecast_origin_date
    FROM features c
    WHERE c.is_canonical_daily_vintage
        AND EXISTS (
            SELECT 1
            FROM features newer
            WHERE newer.city_id = c.city_id
                AND newer.forecast_origin_date = c.forecast_origin_date
                AND newer.has_complete_weather_feature_window
                AND (
                    newer.ingested_at_utc > c.ingested_at_utc
                    OR (
                        newer.ingested_at_utc = c.ingested_at_utc
                        AND newer.ingestion_run_id > c.ingestion_run_id
                    )
                )
        )
)

SELECT * FROM row_violations
UNION ALL
SELECT * FROM canonical_group_violations
UNION ALL
SELECT * FROM canonical_order_violations
