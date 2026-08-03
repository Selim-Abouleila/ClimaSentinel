{{ config(tags=['ml_point_in_time']) }}

-- Training rows must use one canonical eligible feature vintage, align each
-- target to its exact future calendar day, and learn labels only after archive/reanalysis
-- made those outcomes available.

WITH joined AS (
    SELECT
        t.*,
        f.ingestion_run_id AS source_feature_run_id,

        labels_1d.city_id AS source_label_city_1d,
        labels_1d.realized_heat_score AS source_heat_score_1d,
        labels_1d.realized_rain_score AS source_rain_score_1d,
        labels_1d.heat_label_available_at_utc
            AS source_heat_label_available_at_utc_1d,
        labels_1d.rain_label_available_at_utc
            AS source_rain_label_available_at_utc_1d,
        labels_1d.labels_available_at_utc AS source_labels_available_at_utc_1d,

        labels_2d.city_id AS source_label_city_2d,
        labels_2d.realized_heat_score AS source_heat_score_2d,
        labels_2d.realized_rain_score AS source_rain_score_2d,
        labels_2d.heat_label_available_at_utc
            AS source_heat_label_available_at_utc_2d,
        labels_2d.rain_label_available_at_utc
            AS source_rain_label_available_at_utc_2d,
        labels_2d.labels_available_at_utc AS source_labels_available_at_utc_2d,

        labels_3d.city_id AS source_label_city_3d,
        labels_3d.realized_heat_score AS source_heat_score_3d,
        labels_3d.realized_rain_score AS source_rain_score_3d,
        labels_3d.heat_label_available_at_utc
            AS source_heat_label_available_at_utc_3d,
        labels_3d.rain_label_available_at_utc
            AS source_rain_label_available_at_utc_3d,
        labels_3d.labels_available_at_utc AS source_labels_available_at_utc_3d
    FROM {{ ref('mart_ml_training_examples') }} t
    LEFT JOIN {{ ref('mart_ml_forecast_features_vintage') }} f
        ON t.ingestion_run_id = f.ingestion_run_id
        AND t.city_id = f.city_id
        AND t.forecast_origin_date = f.forecast_origin_date
        AND f.is_canonical_daily_vintage
        AND f.has_expected_horizon_dates
        AND f.has_complete_weather_feature_window
    LEFT JOIN {{ ref('mart_city_realized_weather_daily') }} labels_1d
        ON t.city_id = labels_1d.city_id
        AND t.target_date_1d = labels_1d.valid_date
    LEFT JOIN {{ ref('mart_city_realized_weather_daily') }} labels_2d
        ON t.city_id = labels_2d.city_id
        AND t.target_date_2d = labels_2d.valid_date
    LEFT JOIN {{ ref('mart_city_realized_weather_daily') }} labels_3d
        ON t.city_id = labels_3d.city_id
        AND t.target_date_3d = labels_3d.valid_date
)

SELECT
    ingestion_run_id,
    city_id,
    forecast_origin_date,
    target_date_1d,
    target_date_2d,
    target_date_3d
FROM joined
WHERE source_feature_run_id IS NULL
    OR NOT is_canonical_daily_vintage
    OR NOT has_expected_horizon_dates
    OR NOT has_complete_weather_feature_window
    OR target_date_1d != DATE_ADD(forecast_origin_date, INTERVAL 1 DAY)
    OR target_date_2d != DATE_ADD(forecast_origin_date, INTERVAL 2 DAY)
    OR target_date_3d != DATE_ADD(forecast_origin_date, INTERVAL 3 DAY)
    OR source_label_city_1d IS NULL
    OR source_label_city_2d IS NULL
    OR source_label_city_3d IS NULL
    OR future_heat_score_1d IS DISTINCT FROM source_heat_score_1d
    OR future_heat_score_2d IS DISTINCT FROM source_heat_score_2d
    OR future_heat_score_3d IS DISTINCT FROM source_heat_score_3d
    OR future_rain_score_1d IS DISTINCT FROM source_rain_score_1d
    OR future_rain_score_2d IS DISTINCT FROM source_rain_score_2d
    OR future_rain_score_3d IS DISTINCT FROM source_rain_score_3d
    OR heat_label_available_at_utc_1d
        IS DISTINCT FROM source_heat_label_available_at_utc_1d
    OR heat_label_available_at_utc_2d
        IS DISTINCT FROM source_heat_label_available_at_utc_2d
    OR heat_label_available_at_utc_3d
        IS DISTINCT FROM source_heat_label_available_at_utc_3d
    OR rain_label_available_at_utc_1d
        IS DISTINCT FROM source_rain_label_available_at_utc_1d
    OR rain_label_available_at_utc_2d
        IS DISTINCT FROM source_rain_label_available_at_utc_2d
    OR rain_label_available_at_utc_3d
        IS DISTINCT FROM source_rain_label_available_at_utc_3d
    OR labels_available_at_utc_1d
        IS DISTINCT FROM source_labels_available_at_utc_1d
    OR labels_available_at_utc_2d
        IS DISTINCT FROM source_labels_available_at_utc_2d
    OR labels_available_at_utc_3d
        IS DISTINCT FROM source_labels_available_at_utc_3d
    OR heat_label_available_at_utc_1d <= ingested_at_utc
    OR heat_label_available_at_utc_2d <= ingested_at_utc
    OR heat_label_available_at_utc_3d <= ingested_at_utc
    OR rain_label_available_at_utc_1d <= ingested_at_utc
    OR rain_label_available_at_utc_2d <= ingested_at_utc
    OR rain_label_available_at_utc_3d <= ingested_at_utc
    OR labels_available_at_utc_1d <= ingested_at_utc
    OR labels_available_at_utc_2d <= ingested_at_utc
    OR labels_available_at_utc_3d <= ingested_at_utc
    OR training_labels_available_at_utc IS DISTINCT FROM GREATEST(
        labels_available_at_utc_1d,
        labels_available_at_utc_2d,
        labels_available_at_utc_3d
    )
    OR label_source != 'open_meteo_era5'
    OR supported_target_components != 'heat,rain'
    OR unsupported_target_components != 'wind,air,river'
    OR canonical_vintage_rule
        != 'latest_complete_weather_vintage_per_city_local_origin_date'
