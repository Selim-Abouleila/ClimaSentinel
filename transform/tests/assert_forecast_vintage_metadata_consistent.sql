{{ config(tags=['forecast_vintage']) }}

-- Hard point-in-time invariants shared by every vintage model. The provider
-- valid date is city-local, so the origin date must use that same city's IANA
-- timezone rather than UTC calendar time.

WITH city_time_zones AS (
    SELECT *
    FROM UNNEST([
        STRUCT('paris_fr' AS city_id, 'Europe/Paris' AS time_zone),
        STRUCT('london_gb' AS city_id, 'Europe/London' AS time_zone),
        STRUCT('madrid_es' AS city_id, 'Europe/Madrid' AS time_zone),
        STRUCT('berlin_de' AS city_id, 'Europe/Berlin' AS time_zone),
        STRUCT('rome_it' AS city_id, 'Europe/Rome' AS time_zone),
        STRUCT('amsterdam_nl' AS city_id, 'Europe/Amsterdam' AS time_zone),
        STRUCT('athens_gr' AS city_id, 'Europe/Athens' AS time_zone),
        STRUCT('warsaw_pl' AS city_id, 'Europe/Warsaw' AS time_zone),
        STRUCT('lisbon_pt' AS city_id, 'Europe/Lisbon' AS time_zone),
        STRUCT('stockholm_se' AS city_id, 'Europe/Stockholm' AS time_zone)
    ])
),

vintage_rows AS (
    SELECT
        'stg_weather_forecast_hourly_vintage' AS model_name,
        ingestion_run_id,
        city_id,
        ingested_at_utc,
        forecast_origin_time_zone,
        forecast_origin_date,
        valid_date,
        horizon_days
    FROM {{ ref('stg_weather_forecast_hourly_vintage') }}

    UNION ALL

    SELECT
        'stg_city_daily_weather_vintage',
        ingestion_run_id,
        city_id,
        ingested_at_utc,
        forecast_origin_time_zone,
        forecast_origin_date,
        valid_date,
        horizon_days
    FROM {{ ref('stg_city_daily_weather_vintage') }}

    UNION ALL

    SELECT
        'stg_air_quality_hourly_vintage',
        ingestion_run_id,
        city_id,
        ingested_at_utc,
        forecast_origin_time_zone,
        forecast_origin_date,
        valid_date,
        horizon_days
    FROM {{ ref('stg_air_quality_hourly_vintage') }}

    UNION ALL

    SELECT
        'stg_city_daily_air_quality_vintage',
        ingestion_run_id,
        city_id,
        ingested_at_utc,
        forecast_origin_time_zone,
        forecast_origin_date,
        valid_date,
        horizon_days
    FROM {{ ref('stg_city_daily_air_quality_vintage') }}

    UNION ALL

    SELECT
        'stg_flood_daily_vintage',
        ingestion_run_id,
        city_id,
        ingested_at_utc,
        forecast_origin_time_zone,
        forecast_origin_date,
        valid_date,
        horizon_days
    FROM {{ ref('stg_flood_daily_vintage') }}

    UNION ALL

    SELECT
        'stg_city_signal_vintage',
        ingestion_run_id,
        city_id,
        ingested_at_utc,
        forecast_origin_time_zone,
        forecast_origin_date,
        valid_date,
        horizon_days
    FROM {{ ref('stg_city_signal_vintage') }}
)

SELECT
    v.model_name,
    v.ingestion_run_id,
    v.city_id,
    v.ingested_at_utc,
    v.forecast_origin_time_zone,
    v.forecast_origin_date,
    v.valid_date,
    v.horizon_days
FROM vintage_rows v
LEFT JOIN city_time_zones z
    ON v.city_id = z.city_id
WHERE v.ingestion_run_id IS NULL
   OR v.city_id IS NULL
   OR v.ingested_at_utc IS NULL
   OR v.forecast_origin_time_zone IS NULL
   OR v.forecast_origin_date IS NULL
   OR v.valid_date IS NULL
   OR v.horizon_days IS NULL
   OR z.city_id IS NULL
   OR v.forecast_origin_time_zone != z.time_zone
   OR v.forecast_origin_date != DATE(v.ingested_at_utc, z.time_zone)
   OR v.horizon_days != DATE_DIFF(
       v.valid_date,
       DATE(v.ingested_at_utc, z.time_zone),
       DAY
   )
