{{ config(tags=['forecast_vintage']) }}

-- The loader assigns one ingestion timestamp to a run and reuses it across
-- weather, AQ, and flood. More than one timestamp for a run would make the
-- point-in-time origin ambiguous and must be investigated.

WITH source_timestamps AS (
    SELECT ingestion_run_id, ingested_at_utc
    FROM {{ source('raw', 'weather_forecast_hourly') }}

    UNION ALL

    SELECT ingestion_run_id, ingested_at_utc
    FROM {{ source('raw', 'air_quality_hourly') }}

    UNION ALL

    SELECT ingestion_run_id, ingested_at_utc
    FROM {{ source('raw', 'flood_daily') }}
)

SELECT
    ingestion_run_id,
    COUNT(DISTINCT ingested_at_utc) AS ingestion_timestamp_count
FROM source_timestamps
GROUP BY ingestion_run_id
HAVING COUNT(DISTINCT ingested_at_utc) != 1
