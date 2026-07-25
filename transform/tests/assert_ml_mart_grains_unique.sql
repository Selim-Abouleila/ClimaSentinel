{{ config(tags=['ml_point_in_time']) }}

-- Every ML mart must honor its documented grain. Keeping this as one singular
-- test makes duplicate-key failures visible even when composite-key generic
-- tests are unavailable.

WITH forecast_duplicates AS (
    SELECT
        'mart_ml_forecast_features_vintage' AS model_name,
        CAST(ingestion_run_id AS STRING) AS key_1,
        city_id AS key_2,
        CAST(forecast_origin_date AS STRING) AS key_3,
        COUNT(*) AS row_count
    FROM {{ ref('mart_ml_forecast_features_vintage') }}
    GROUP BY ingestion_run_id, city_id, forecast_origin_date
    HAVING COUNT(*) != 1
),

realized_duplicates AS (
    SELECT
        'mart_city_realized_weather_daily' AS model_name,
        city_id AS key_1,
        CAST(valid_date AS STRING) AS key_2,
        CAST(NULL AS STRING) AS key_3,
        COUNT(*) AS row_count
    FROM {{ ref('mart_city_realized_weather_daily') }}
    GROUP BY city_id, valid_date
    HAVING COUNT(*) != 1
),

training_duplicates AS (
    SELECT
        'mart_ml_training_examples' AS model_name,
        city_id AS key_1,
        CAST(forecast_origin_date AS STRING) AS key_2,
        CAST(NULL AS STRING) AS key_3,
        COUNT(*) AS row_count
    FROM {{ ref('mart_ml_training_examples') }}
    GROUP BY city_id, forecast_origin_date
    HAVING COUNT(*) != 1
),

serving_duplicates AS (
    SELECT
        'mart_ml_serving_features_current' AS model_name,
        city_id AS key_1,
        CAST(NULL AS STRING) AS key_2,
        CAST(NULL AS STRING) AS key_3,
        COUNT(*) AS row_count
    FROM {{ ref('mart_ml_serving_features_current') }}
    GROUP BY city_id
    HAVING COUNT(*) != 1
)

SELECT * FROM forecast_duplicates
UNION ALL
SELECT * FROM realized_duplicates
UNION ALL
SELECT * FROM training_duplicates
UNION ALL
SELECT * FROM serving_duplicates
