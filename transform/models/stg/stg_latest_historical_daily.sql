-- stg_latest_historical_daily.sql
-- Deduplicates raw.historical_weather_daily: keeps only the freshest ERA5 reading
-- for each (city_id, date) pair based on ingestion timestamp.
-- ERA5 data has a ~5-day publication lag; the ingest fetcher offsets by 6-12 days.

WITH ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY city_id, date
            ORDER BY ingested_at_utc DESC
        ) AS _row_num
    FROM {{ source('raw', 'historical_weather_daily') }}
)

SELECT
    city_id,
    date,
    temperature_2m_mean,
    temperature_2m_max,
    temperature_2m_min,
    precipitation_sum_mm,
    wind_speed_10m_max,
    ingestion_run_id,
    ingested_at_utc
FROM ranked
WHERE _row_num = 1
