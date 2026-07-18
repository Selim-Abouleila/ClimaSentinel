{{ config(tags=['forecast_vintage']) }}

-- Presence flags and optional-source timestamps must describe the exact same
-- ingestion vintage as the weather anchor.

SELECT
    ingestion_run_id,
    city_id,
    valid_date,
    ingested_at_utc,
    has_air_quality_forecast,
    air_quality_ingested_at_utc,
    has_flood_forecast,
    flood_ingested_at_utc
FROM {{ ref('stg_city_signal_vintage') }}
WHERE has_air_quality_forecast != (air_quality_ingested_at_utc IS NOT NULL)
   OR has_flood_forecast != (flood_ingested_at_utc IS NOT NULL)
   OR (
       has_air_quality_forecast
       AND air_quality_ingested_at_utc != ingested_at_utc
   )
   OR (
       has_flood_forecast
       AND flood_ingested_at_utc != ingested_at_utc
   )
