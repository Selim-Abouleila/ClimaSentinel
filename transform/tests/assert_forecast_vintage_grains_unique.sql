{{ config(tags=['forecast_vintage']) }}

-- dbt core has no composite-key uniqueness test. Return every duplicate
-- vintage grain across the six new staging models.

WITH violations AS (
    SELECT
        'stg_weather_forecast_hourly_vintage' AS model_name,
        ingestion_run_id,
        city_id,
        CAST(valid_ts_utc AS STRING) AS valid_key,
        COUNT(*) AS row_count
    FROM {{ ref('stg_weather_forecast_hourly_vintage') }}
    GROUP BY ingestion_run_id, city_id, valid_ts_utc
    HAVING COUNT(*) > 1

    UNION ALL

    SELECT
        'stg_city_daily_weather_vintage',
        ingestion_run_id,
        city_id,
        CAST(valid_date AS STRING),
        COUNT(*)
    FROM {{ ref('stg_city_daily_weather_vintage') }}
    GROUP BY ingestion_run_id, city_id, valid_date
    HAVING COUNT(*) > 1

    UNION ALL

    SELECT
        'stg_air_quality_hourly_vintage',
        ingestion_run_id,
        city_id,
        CAST(valid_ts_utc AS STRING),
        COUNT(*)
    FROM {{ ref('stg_air_quality_hourly_vintage') }}
    GROUP BY ingestion_run_id, city_id, valid_ts_utc
    HAVING COUNT(*) > 1

    UNION ALL

    SELECT
        'stg_city_daily_air_quality_vintage',
        ingestion_run_id,
        city_id,
        CAST(valid_date AS STRING),
        COUNT(*)
    FROM {{ ref('stg_city_daily_air_quality_vintage') }}
    GROUP BY ingestion_run_id, city_id, valid_date
    HAVING COUNT(*) > 1

    UNION ALL

    SELECT
        'stg_flood_daily_vintage',
        ingestion_run_id,
        city_id,
        CAST(valid_date AS STRING),
        COUNT(*)
    FROM {{ ref('stg_flood_daily_vintage') }}
    GROUP BY ingestion_run_id, city_id, valid_date
    HAVING COUNT(*) > 1

    UNION ALL

    SELECT
        'stg_city_signal_vintage',
        ingestion_run_id,
        city_id,
        CAST(valid_date AS STRING),
        COUNT(*)
    FROM {{ ref('stg_city_signal_vintage') }}
    GROUP BY ingestion_run_id, city_id, valid_date
    HAVING COUNT(*) > 1
)

SELECT *
FROM violations
