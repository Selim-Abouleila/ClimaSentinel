{{ config(tags=['ml_point_in_time']) }}

-- Reverse coverage closes the empty/subset loophole left by forward-only
-- invariants: every source row that satisfies a mart's contract must appear in
-- that mart.

WITH expected_training AS (
    SELECT
        feature.ingestion_run_id,
        feature.city_id,
        feature.forecast_origin_date
    FROM {{ ref('mart_ml_forecast_features_vintage') }} feature
    INNER JOIN {{ ref('mart_city_realized_weather_daily') }} labels_1d
        ON feature.city_id = labels_1d.city_id
        AND labels_1d.valid_date = DATE_ADD(
            feature.forecast_origin_date,
            INTERVAL 1 DAY
        )
    INNER JOIN {{ ref('mart_city_realized_weather_daily') }} labels_2d
        ON feature.city_id = labels_2d.city_id
        AND labels_2d.valid_date = DATE_ADD(
            feature.forecast_origin_date,
            INTERVAL 2 DAY
        )
    INNER JOIN {{ ref('mart_city_realized_weather_daily') }} labels_3d
        ON feature.city_id = labels_3d.city_id
        AND labels_3d.valid_date = DATE_ADD(
            feature.forecast_origin_date,
            INTERVAL 3 DAY
        )
    WHERE feature.is_canonical_daily_vintage
        AND feature.has_expected_horizon_dates
        AND feature.has_complete_weather_feature_window
        AND labels_1d.has_mature_realized_labels
        AND labels_2d.has_mature_realized_labels
        AND labels_3d.has_mature_realized_labels
        AND labels_1d.heat_label_available_at_utc > feature.ingested_at_utc
        AND labels_1d.rain_label_available_at_utc > feature.ingested_at_utc
        AND labels_2d.heat_label_available_at_utc > feature.ingested_at_utc
        AND labels_2d.rain_label_available_at_utc > feature.ingested_at_utc
        AND labels_3d.heat_label_available_at_utc > feature.ingested_at_utc
        AND labels_3d.rain_label_available_at_utc > feature.ingested_at_utc
),

expected_serving AS (
    SELECT
        ingestion_run_id,
        city_id,
        forecast_origin_date
    FROM {{ ref('mart_ml_forecast_features_vintage') }}
    WHERE is_canonical_daily_vintage
        AND has_expected_horizon_dates
        AND has_complete_weather_feature_window
        AND forecast_origin_date = DATE(
            CURRENT_TIMESTAMP(),
            forecast_origin_time_zone
        )
),

missing_realized AS (
    SELECT
        'mart_city_realized_weather_daily' AS contract_name,
        source.city_id AS key_1,
        CAST(source.date AS STRING) AS key_2,
        CAST(NULL AS STRING) AS key_3
    FROM {{ ref('stg_latest_historical_daily') }} source
    LEFT JOIN {{ ref('mart_city_realized_weather_daily') }} realized
        ON source.city_id = realized.city_id
        AND source.date = realized.valid_date
    WHERE realized.city_id IS NULL
),

missing_training AS (
    SELECT
        'mart_ml_training_examples' AS contract_name,
        expected.city_id AS key_1,
        CAST(expected.forecast_origin_date AS STRING) AS key_2,
        CAST(expected.ingestion_run_id AS STRING) AS key_3
    FROM expected_training expected
    LEFT JOIN {{ ref('mart_ml_training_examples') }} training
        ON expected.ingestion_run_id = training.ingestion_run_id
        AND expected.city_id = training.city_id
        AND expected.forecast_origin_date = training.forecast_origin_date
    WHERE training.ingestion_run_id IS NULL
),

missing_serving AS (
    SELECT
        'mart_ml_serving_features_current' AS contract_name,
        expected.city_id AS key_1,
        CAST(expected.forecast_origin_date AS STRING) AS key_2,
        CAST(expected.ingestion_run_id AS STRING) AS key_3
    FROM expected_serving expected
    LEFT JOIN {{ ref('mart_ml_serving_features_current') }} serving
        ON expected.ingestion_run_id = serving.ingestion_run_id
        AND expected.city_id = serving.city_id
        AND expected.forecast_origin_date = serving.forecast_origin_date
    WHERE serving.ingestion_run_id IS NULL
)

SELECT * FROM missing_realized
UNION ALL
SELECT * FROM missing_training
UNION ALL
SELECT * FROM missing_serving
