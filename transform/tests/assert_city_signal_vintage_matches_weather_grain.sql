{{ config(tags=['forecast_vintage']) }}

-- The unified signal model is weather-anchored. Its key set must match the
-- daily weather vintage key set exactly: no row loss and no row multiplication.

SELECT
    COALESCE(w.ingestion_run_id, s.ingestion_run_id) AS ingestion_run_id,
    COALESCE(w.city_id, s.city_id) AS city_id,
    COALESCE(w.valid_date, s.valid_date) AS valid_date,
    CASE
        WHEN w.ingestion_run_id IS NULL THEN 'unexpected_unified_key'
        WHEN s.ingestion_run_id IS NULL THEN 'missing_unified_key'
    END AS violation
FROM {{ ref('stg_city_daily_weather_vintage') }} w
FULL OUTER JOIN {{ ref('stg_city_signal_vintage') }} s
    ON w.ingestion_run_id = s.ingestion_run_id
    AND w.city_id = s.city_id
    AND w.valid_date = s.valid_date
WHERE w.ingestion_run_id IS NULL
   OR s.ingestion_run_id IS NULL
