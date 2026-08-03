-- Every v2 operational relation must derive from exactly the run selected
-- across all raw source families. Empty source models are valid for a partial
-- run; borrowing rows from an older run is not.

WITH selected_run AS (
    SELECT *
    FROM {{ ref('stg_operational_run_v2') }}
),

source_rows AS (
    SELECT
        'weather_daily_v2' AS model_name,
        ingestion_run_id
    FROM {{ ref('stg_city_daily_weather_v2') }}

    UNION ALL

    SELECT 'air_quality_daily_v2', ingestion_run_id
    FROM {{ ref('stg_city_daily_air_quality_v2') }}

    UNION ALL

    SELECT 'flood_daily_v2', ingestion_run_id
    FROM {{ ref('stg_flood_daily_v2') }}

    UNION ALL

    SELECT 'signal_input_v2', operational_ingestion_run_id
    FROM {{ ref('stg_city_signal_input_v2') }}

    UNION ALL

    SELECT 'score_history_v2', operational_ingestion_run_id
    FROM {{ ref('mart_city_score_history_v2') }}

    UNION ALL

    SELECT 'score_current_v2', operational_ingestion_run_id
    FROM {{ ref('mart_city_score_current_v2') }}

    UNION ALL

    SELECT 'score_detail_v2', operational_ingestion_run_id
    FROM {{ ref('mart_city_score_detail_v2') }}
),

run_id_violations AS (
    SELECT
        'unexpected_ingestion_run_id' AS violation,
        source_rows.model_name,
        source_rows.ingestion_run_id
    FROM source_rows
    CROSS JOIN selected_run
    WHERE source_rows.ingestion_run_id IS DISTINCT FROM
        selected_run.operational_ingestion_run_id
),

source_presence AS (
    SELECT
        EXISTS (
            SELECT 1
            FROM {{ source('raw', 'weather_forecast_hourly') }} AS raw_weather
            WHERE CAST(raw_weather.ingestion_run_id AS STRING)
                = selected_run.operational_ingestion_run_id
                AND raw_weather.city_id IN (
                    SELECT city_id FROM {{ ref('city_signal_monitoring') }}
                )
        ) AS has_weather_rows,
        EXISTS (
            SELECT 1
            FROM {{ source('raw', 'air_quality_hourly') }} AS raw_air_quality
            WHERE CAST(raw_air_quality.ingestion_run_id AS STRING)
                = selected_run.operational_ingestion_run_id
                AND raw_air_quality.city_id IN (
                    SELECT city_id FROM {{ ref('city_signal_monitoring') }}
                )
        ) AS has_air_quality_rows,
        EXISTS (
            SELECT 1
            FROM {{ source('raw', 'flood_daily') }} AS raw_flood
            WHERE CAST(raw_flood.ingestion_run_id AS STRING)
                = selected_run.operational_ingestion_run_id
                AND raw_flood.city_id IN (
                    SELECT city_id FROM {{ ref('city_signal_monitoring') }}
                )
        ) AS has_flood_rows,
        EXISTS (
            SELECT 1
            FROM {{ source('raw', 'historical_weather_daily') }} AS raw_history
            WHERE CAST(raw_history.ingestion_run_id AS STRING)
                = selected_run.operational_ingestion_run_id
                AND raw_history.city_id IN (
                    SELECT city_id FROM {{ ref('city_signal_monitoring') }}
                )
        ) AS has_historical_weather_rows
    FROM selected_run
),

presence_violations AS (
    SELECT
        'source_presence_flag_mismatch' AS violation,
        'stg_operational_run_v2' AS model_name,
        selected_run.operational_ingestion_run_id AS ingestion_run_id
    FROM selected_run
    CROSS JOIN source_presence
    WHERE selected_run.run_has_weather_source IS DISTINCT FROM has_weather_rows
        OR selected_run.run_has_air_quality_source
            IS DISTINCT FROM has_air_quality_rows
        OR selected_run.run_has_flood_source IS DISTINCT FROM has_flood_rows
        OR selected_run.run_has_historical_weather_source
            IS DISTINCT FROM has_historical_weather_rows
),

grain_violations AS (
    SELECT
        'duplicate_source_grain' AS violation,
        'weather_daily_v2' AS model_name,
        ingestion_run_id
    FROM {{ ref('stg_city_daily_weather_v2') }}
    GROUP BY ingestion_run_id, city_id, date
    HAVING COUNT(*) != 1

    UNION ALL

    SELECT
        'duplicate_source_grain',
        'air_quality_daily_v2',
        ingestion_run_id
    FROM {{ ref('stg_city_daily_air_quality_v2') }}
    GROUP BY ingestion_run_id, city_id, date
    HAVING COUNT(*) != 1

    UNION ALL

    SELECT
        'duplicate_source_grain',
        'flood_daily_v2',
        ingestion_run_id
    FROM {{ ref('stg_flood_daily_v2') }}
    GROUP BY ingestion_run_id, city_id, date
    HAVING COUNT(*) != 1

    UNION ALL

    SELECT
        'duplicate_source_grain',
        'signal_input_v2',
        operational_ingestion_run_id
    FROM {{ ref('stg_city_signal_input_v2') }}
    GROUP BY operational_ingestion_run_id, city_id, date
    HAVING COUNT(*) != 1
),

availability_metadata_violations AS (
    SELECT
        'source_availability_metadata_mismatch' AS violation,
        'signal_input_v2' AS model_name,
        operational_ingestion_run_id AS ingestion_run_id
    FROM {{ ref('stg_city_signal_input_v2') }}
    WHERE weather_source_available
        IS DISTINCT FROM (weather_ingested_at_utc IS NOT NULL)
        OR air_quality_source_available
            IS DISTINCT FROM (air_quality_ingested_at_utc IS NOT NULL)
        OR flood_source_available
            IS DISTINCT FROM (flood_ingested_at_utc IS NOT NULL)
)

SELECT * FROM run_id_violations
UNION ALL
SELECT * FROM presence_violations
UNION ALL
SELECT * FROM grain_violations
UNION ALL
SELECT * FROM availability_metadata_violations
