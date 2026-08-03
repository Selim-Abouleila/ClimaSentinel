{{ config(
    materialized='table'
) }}

-- One exact operational snapshot selected across every raw source family.
-- A partial run is intentionally eligible: its missing source flags make the
-- gap visible instead of allowing a latest-per-timestamp fallback to older data.

WITH source_rows AS (
    SELECT
        CAST(ingestion_run_id AS STRING) AS ingestion_run_id,
        ingested_at_utc,
        'weather' AS source_name
    FROM {{ source('raw', 'weather_forecast_hourly') }}
    WHERE ingestion_run_id IS NOT NULL
        AND ingested_at_utc IS NOT NULL
        AND city_id IN (SELECT city_id FROM {{ ref('city_signal_monitoring') }})

    UNION ALL

    SELECT
        CAST(ingestion_run_id AS STRING),
        ingested_at_utc,
        'air_quality'
    FROM {{ source('raw', 'air_quality_hourly') }}
    WHERE ingestion_run_id IS NOT NULL
        AND ingested_at_utc IS NOT NULL
        AND city_id IN (SELECT city_id FROM {{ ref('city_signal_monitoring') }})

    UNION ALL

    SELECT
        CAST(ingestion_run_id AS STRING),
        ingested_at_utc,
        'flood'
    FROM {{ source('raw', 'flood_daily') }}
    WHERE ingestion_run_id IS NOT NULL
        AND ingested_at_utc IS NOT NULL
        AND city_id IN (SELECT city_id FROM {{ ref('city_signal_monitoring') }})

    UNION ALL

    SELECT
        CAST(ingestion_run_id AS STRING),
        ingested_at_utc,
        'historical_weather'
    FROM {{ source('raw', 'historical_weather_daily') }}
    WHERE ingestion_run_id IS NOT NULL
        AND ingested_at_utc IS NOT NULL
        AND city_id IN (SELECT city_id FROM {{ ref('city_signal_monitoring') }})
),

runs AS (
    SELECT
        ingestion_run_id AS operational_ingestion_run_id,
        MAX(ingested_at_utc) AS operational_ingested_at_utc,
        COUNTIF(source_name = 'weather') > 0 AS run_has_weather_source,
        COUNTIF(source_name = 'air_quality') > 0 AS run_has_air_quality_source,
        COUNTIF(source_name = 'flood') > 0 AS run_has_flood_source,
        COUNTIF(source_name = 'historical_weather') > 0
            AS run_has_historical_weather_source,
        COUNT(DISTINCT source_name) AS run_source_count
    FROM source_rows
    GROUP BY ingestion_run_id
)

SELECT *
FROM runs
QUALIFY ROW_NUMBER() OVER (
    ORDER BY operational_ingested_at_utc DESC, operational_ingestion_run_id DESC
) = 1
