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
        raw_weather.*,
        forecast_city.forecast_origin_time_zone,
        ROW_NUMBER() OVER (
            PARTITION BY
                raw_weather.ingestion_run_id,
                raw_weather.city_id,
                raw_weather.valid_ts_utc
            ORDER BY
                raw_weather.ingested_at_utc DESC,
                raw_weather.temperature_2m DESC,
                raw_weather.precipitation_mm DESC,
                raw_weather.wind_speed_10m DESC,
                raw_weather.wind_gusts_10m DESC,
                raw_weather.weather_code DESC
        ) AS _row_num
    FROM {{ source('raw', 'weather_forecast_hourly') }} AS raw_weather
    INNER JOIN {{ ref('forecast_city_allowlist') }} AS forecast_city
        ON raw_weather.city_id = forecast_city.city_id
)

SELECT
    ingestion_run_id,
    ingested_at_utc,
    forecast_origin_time_zone,
    DATE(ingested_at_utc, forecast_origin_time_zone) AS forecast_origin_date,
    city_id,
    valid_ts_utc,
    DATE(valid_ts_utc) AS valid_date,
    DATE_DIFF(
        DATE(valid_ts_utc),
        DATE(ingested_at_utc, forecast_origin_time_zone),
        DAY
    ) AS horizon_days,
    temperature_2m,
    precipitation_mm,
    wind_speed_10m,
    wind_gusts_10m,
    weather_code
FROM ranked
WHERE _row_num = 1
