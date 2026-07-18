{{ config(tags=['forecast_vintage']) }}

-- Preserves every weather forecast retrieval as a separate vintage.
--
-- Grain: one row per (ingestion_run_id, city_id, valid_ts_utc).
-- `ingested_at_utc` is the ingestion-run start timestamp and serves as the
-- ClimaSentinel availability proxy. It is not Open-Meteo's model issue time.
--
-- Raw retries can create duplicate natural keys inside one ingestion run.
-- They are deduplicated here without collapsing separate forecast runs.

WITH ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY ingestion_run_id, city_id, valid_ts_utc
            ORDER BY
                ingested_at_utc DESC,
                temperature_2m DESC,
                precipitation_mm DESC,
                wind_speed_10m DESC,
                wind_gusts_10m DESC,
                weather_code DESC
        ) AS _row_num
    FROM {{ source('raw', 'weather_forecast_hourly') }}
)

SELECT
    ingestion_run_id,
    ingested_at_utc,
    DATE(ingested_at_utc) AS forecast_origin_date,
    city_id,
    valid_ts_utc,
    DATE(valid_ts_utc) AS valid_date,
    DATE_DIFF(
        DATE(valid_ts_utc),
        DATE(ingested_at_utc),
        DAY
    ) AS horizon_days,
    temperature_2m,
    precipitation_mm,
    wind_speed_10m,
    wind_gusts_10m,
    weather_code
FROM ranked
WHERE _row_num = 1
