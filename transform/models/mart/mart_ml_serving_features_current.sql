{{ config(
    materialized='view',
    tags=['ml_point_in_time']
) }}

-- Latest point-in-time-safe feature vector for operational model serving.
--
-- Grain: at most one row per city_id. Only a city-local current-day origin is
-- eligible. Reusing yesterday's row would silently shift plus_1d from
-- "tomorrow" to "today", so the view intentionally returns no row before the
-- daily refresh or during an ingestion outage.

WITH eligible AS (
    SELECT
        f.*,
        DATE_DIFF(
            DATE(CURRENT_TIMESTAMP(), f.forecast_origin_time_zone),
            f.forecast_origin_date,
            DAY
        ) AS forecast_age_days,
        ROW_NUMBER() OVER (
            PARTITION BY f.city_id
            ORDER BY
                f.forecast_origin_date DESC,
                f.ingested_at_utc DESC,
                f.ingestion_run_id DESC
        ) AS _serving_rank
    FROM {{ ref('mart_ml_forecast_features_vintage') }} f
    WHERE f.is_canonical_daily_vintage
        AND f.has_expected_horizon_dates
        AND f.has_complete_weather_feature_window
        AND f.forecast_origin_date = DATE(
            CURRENT_TIMESTAMP(),
            f.forecast_origin_time_zone
        )
)

SELECT * EXCEPT (_serving_rank)
FROM eligible
WHERE _serving_rank = 1
