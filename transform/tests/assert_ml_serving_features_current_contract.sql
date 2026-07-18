{{ config(tags=['ml_point_in_time']) }}

-- Serving may expose only the latest canonical feature row for the current
-- city-local origin date. If today's eligible run does not exist, the correct
-- behavior is to expose no row for that city.

WITH serving AS (
    SELECT *
    FROM {{ ref('mart_ml_serving_features_current') }}
),

source_features AS (
    SELECT *
    FROM {{ ref('mart_ml_forecast_features_vintage') }}
)

SELECT
    s.ingestion_run_id,
    s.city_id,
    s.forecast_origin_date,
    s.forecast_age_days
FROM serving s
LEFT JOIN source_features source
    ON s.ingestion_run_id = source.ingestion_run_id
    AND s.city_id = source.city_id
    AND s.forecast_origin_date = source.forecast_origin_date
WHERE source.ingestion_run_id IS NULL
    OR NOT s.is_canonical_daily_vintage
    OR NOT s.has_expected_horizon_dates
    OR NOT s.has_complete_weather_feature_window
    OR s.forecast_age_days IS DISTINCT FROM DATE_DIFF(
        DATE(CURRENT_TIMESTAMP(), s.forecast_origin_time_zone),
        s.forecast_origin_date,
        DAY
    )
    OR s.forecast_age_days != 0
    OR EXISTS (
        SELECT 1
        FROM source_features newer
        WHERE newer.city_id = s.city_id
            AND newer.is_canonical_daily_vintage
            AND newer.has_expected_horizon_dates
            AND newer.has_complete_weather_feature_window
            AND newer.forecast_origin_date = DATE(
                CURRENT_TIMESTAMP(),
                newer.forecast_origin_time_zone
            )
            AND (
                newer.forecast_origin_date > s.forecast_origin_date
                OR (
                    newer.forecast_origin_date = s.forecast_origin_date
                    AND newer.ingested_at_utc > s.ingested_at_utc
                )
                OR (
                    newer.forecast_origin_date = s.forecast_origin_date
                    AND newer.ingested_at_utc = s.ingested_at_utc
                    AND newer.ingestion_run_id > s.ingestion_run_id
                )
            )
    )
