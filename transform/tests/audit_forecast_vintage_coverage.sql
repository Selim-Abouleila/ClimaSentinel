{{ config(severity='warn', tags=['forecast_vintage']) }}

-- Coverage anomalies are warnings during the initial backfill audit. They are
-- intentionally not filtered from staging: historical partial responses, the
-- older two-day AQ window, and local-time/DST behavior must remain observable.

WITH daily_anomalies AS (
    SELECT
        'stg_city_daily_weather_vintage' AS model_name,
        ingestion_run_id,
        city_id,
        valid_date,
        horizon_days,
        'hour_or_value_coverage' AS reason
    FROM {{ ref('stg_city_daily_weather_vintage') }}
    WHERE NOT has_24_hour_coverage
       OR NOT has_complete_weather_values
       OR horizon_days NOT BETWEEN 0 AND 6

    UNION ALL

    SELECT
        'stg_city_daily_air_quality_vintage',
        ingestion_run_id,
        city_id,
        valid_date,
        horizon_days,
        'hour_or_value_coverage'
    FROM {{ ref('stg_city_daily_air_quality_vintage') }}
    WHERE NOT has_24_hour_coverage
       OR NOT has_complete_air_quality_values
       OR horizon_days NOT BETWEEN 0 AND 4

    UNION ALL

    SELECT
        'stg_flood_daily_vintage',
        ingestion_run_id,
        city_id,
        valid_date,
        horizon_days,
        'value_or_horizon_coverage'
    FROM {{ ref('stg_flood_daily_vintage') }}
    WHERE NOT has_river_discharge_value
       OR horizon_days NOT BETWEEN 0 AND 6
),

-- Compute per-run statistics first, then filter the materialized values in an
-- outer CTE. This keeps aggregate evaluation separate from the final anomaly
-- relation and avoids the previous BigQuery nested-aggregation error.
run_window_stats AS (
    SELECT
        'stg_city_daily_weather_vintage' AS model_name,
        ingestion_run_id,
        city_id,
        MIN(valid_date) AS first_valid_date,
        MIN(horizon_days) AS min_horizon_days,
        MAX(horizon_days) AS max_horizon_days,
        COUNT(DISTINCT valid_date) AS valid_date_count,
        7 AS expected_valid_date_count,
        0 AS expected_min_horizon_days,
        6 AS expected_max_horizon_days,
        'expected_7_day_window' AS reason
    FROM {{ ref('stg_city_daily_weather_vintage') }}
    GROUP BY ingestion_run_id, city_id

    UNION ALL

    SELECT
        'stg_city_daily_air_quality_vintage',
        ingestion_run_id,
        city_id,
        MIN(valid_date),
        MIN(horizon_days),
        MAX(horizon_days),
        COUNT(DISTINCT valid_date),
        5,
        0,
        4,
        'expected_5_day_window'
    FROM {{ ref('stg_city_daily_air_quality_vintage') }}
    GROUP BY ingestion_run_id, city_id

    UNION ALL

    SELECT
        'stg_flood_daily_vintage',
        ingestion_run_id,
        city_id,
        MIN(valid_date),
        MIN(horizon_days),
        MAX(horizon_days),
        COUNT(DISTINCT valid_date),
        7,
        0,
        6,
        'expected_7_day_window'
    FROM {{ ref('stg_flood_daily_vintage') }}
    GROUP BY ingestion_run_id, city_id
),

run_window_anomalies AS (
    SELECT
        model_name,
        ingestion_run_id,
        city_id,
        first_valid_date AS valid_date,
        min_horizon_days AS horizon_days,
        reason
    FROM run_window_stats
    WHERE valid_date_count != expected_valid_date_count
       OR min_horizon_days != expected_min_horizon_days
       OR max_horizon_days != expected_max_horizon_days
)

SELECT * FROM daily_anomalies
UNION ALL
SELECT * FROM run_window_anomalies
