{{ config(
    materialized='view'
) }}

WITH current_window AS (
    SELECT
        operational_ingestion_run_id,
        operational_ingested_at_utc,
        run_has_weather_source,
        run_has_air_quality_source,
        run_has_flood_source,
        run_has_historical_weather_source,
        run_source_count,
        city_id,
        date,
        global_tipping_score,
        global_score_available,
        primary_driver,
        monitored_factor_count,
        available_factor_count,
        overall_coverage
    FROM {{ ref('mart_city_score_history_v2') }}
    -- Look at the two UTC calendar dates: today and tomorrow.
    WHERE date BETWEEN CURRENT_DATE('UTC')
        AND DATE_ADD(CURRENT_DATE('UTC'), INTERVAL 1 DAY)
),

worst_day AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY city_id
            -- A scored date always wins over an unavailable date. Ties choose
            -- the earliest date so every projected field comes from one row.
            ORDER BY global_score_available DESC, global_tipping_score DESC, date ASC
        ) AS _row_number
    FROM current_window
)

SELECT
    operational_ingestion_run_id,
    operational_ingested_at_utc,
    run_has_weather_source,
    run_has_air_quality_source,
    run_has_flood_source,
    run_has_historical_weather_source,
    run_source_count,
    city_id,
    global_tipping_score AS current_tipping_score,
    primary_driver AS current_primary_driver,
    global_score_available AS current_score_available,
    monitored_factor_count,
    available_factor_count,
    overall_coverage,
    -- Unavailable cities sort after every scored city.
    RANK() OVER (
        ORDER BY global_score_available DESC, global_tipping_score DESC
    ) AS rank
FROM worst_day
WHERE _row_number = 1
ORDER BY current_score_available DESC, rank ASC
