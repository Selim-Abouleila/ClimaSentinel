-- Dates are separated deliberately: no row has a consecutive forecast day.
-- Vary city and month to catch accidental baseline joins on just one key.
WITH scenarios AS (
    SELECT 'paris_fr' AS city_id, DATE '2026-01-02' AS date,
        -5.0 AS temperature_2m_min, 24 AS temperature_2m_value_count,
        FALSE AS heat_monitored, TRUE AS cold_monitored
    UNION ALL SELECT 'paris_fr', DATE '2026-02-02', 4.1, 24, TRUE, TRUE
    UNION ALL SELECT 'paris_fr', DATE '2026-03-02', 5.0, 24, TRUE, TRUE
    UNION ALL SELECT 'paris_fr', DATE '2026-04-02', 0.0, 24, TRUE, TRUE
    UNION ALL SELECT 'negative_normal', DATE '2026-01-02', -25.236, 24, TRUE, TRUE
    UNION ALL SELECT 'missing_min', DATE '2026-01-02', CAST(NULL AS FLOAT64), 24, TRUE, TRUE
    UNION ALL SELECT 'paris_fr', DATE '2026-05-02', -5.0, 24, TRUE, TRUE
    UNION ALL SELECT 'partial_day', DATE '2026-01-02', -5.0, 23, TRUE, TRUE
    UNION ALL SELECT 'empty_day', DATE '2026-01-02', -5.0, 0, TRUE, TRUE
    UNION ALL SELECT 'missing_count', DATE '2026-01-02', -5.0, CAST(NULL AS INT64), TRUE, TRUE
    UNION ALL SELECT 'nan_min', DATE '2026-01-02', CAST('NaN' AS FLOAT64), 24, TRUE, TRUE
    UNION ALL SELECT 'positive_inf_min', DATE '2026-01-02', CAST('+inf' AS FLOAT64), 24, TRUE, TRUE
    UNION ALL SELECT 'negative_inf_min', DATE '2026-01-02', CAST('-inf' AS FLOAT64), 24, TRUE, TRUE
    UNION ALL SELECT 'nan_normal', DATE '2026-01-02', -5.0, 24, TRUE, TRUE
    UNION ALL SELECT 'positive_inf_normal', DATE '2026-01-02', -5.0, 24, TRUE, TRUE
    UNION ALL SELECT 'negative_inf_normal', DATE '2026-01-02', -5.0, 24, TRUE, TRUE
    -- Decimal ties, clipping, and relative cold above/below freezing.
    UNION ALL SELECT 'rounding_score', DATE '2026-01-02', 1.07, 24, TRUE, TRUE
    UNION ALL SELECT 'near_cap', DATE '2026-01-02', -17.69, 24, TRUE, TRUE
    UNION ALL SELECT 'at_cap', DATE '2026-01-02', -17.70, 24, TRUE, TRUE
    UNION ALL SELECT 'above_cap', DATE '2026-01-02', -22.70, 24, TRUE, TRUE
    UNION ALL SELECT 'very_large_anomaly', DATE '2026-01-02', -1e100, 24, TRUE, TRUE
    UNION ALL SELECT 'negative_normal_equal', DATE '2026-01-02', -10.0, 24, TRUE, TRUE
    UNION ALL SELECT 'positive_min', DATE '2026-01-02', 12.0, 24, TRUE, TRUE
    -- Coverage is fractional only when both temperature inputs are finite.
    UNION ALL SELECT 'partial_single', DATE '2026-01-02', -5.0, 1, TRUE, TRUE
    UNION ALL SELECT 'partial_half', DATE '2026-01-02', -5.0, 12, TRUE, TRUE
    UNION ALL SELECT 'negative_count', DATE '2026-01-02', -5.0, -1, FALSE, TRUE
    UNION ALL SELECT 'excessive_count', DATE '2026-01-02', -5.0, 25, TRUE, TRUE
    UNION ALL SELECT 'partial_missing_min', DATE '2026-01-02', CAST(NULL AS FLOAT64), 12, TRUE, TRUE
    UNION ALL SELECT 'partial_nan_normal', DATE '2026-01-02', -5.0, 12, TRUE, TRUE
    -- Monitoring affects the factor while the anomaly stays diagnostic.
    UNION ALL SELECT 'not_monitored', DATE '2026-01-02', -5.0, 24, TRUE, FALSE
    UNION ALL SELECT 'not_monitored_partial', DATE '2026-01-02', -5.0, 12, TRUE, FALSE
    UNION ALL SELECT 'missing_monitoring', DATE '2026-01-02', -5.0, 24, TRUE, CAST(NULL AS BOOL)
    -- Increasing anomalies must produce increasing scores below the cap.
    UNION ALL SELECT 'monotonic_2', DATE '2026-01-02', 0.3, 24, TRUE, TRUE
    UNION ALL SELECT 'monotonic_5', DATE '2026-01-02', -2.7, 24, TRUE, TRUE
    UNION ALL SELECT 'monotonic_10', DATE '2026-01-02', -7.7, 24, TRUE, TRUE
)

SELECT
    'cold-anomaly-fixture' AS operational_ingestion_run_id,
    TIMESTAMP '2026-01-01 06:00:00+00' AS operational_ingested_at_utc,
    TRUE AS run_has_weather_source,
    TRUE AS run_has_air_quality_source,
    TRUE AS run_has_flood_source,
    FALSE AS run_has_historical_weather_source,
    3 AS run_source_count,
    scenarios.city_id,
    scenarios.date,
    scenarios.heat_monitored,
    scenarios.cold_monitored,
    TRUE AS wind_monitored,
    TRUE AS rain_monitored,
    TRUE AS air_monitored,
    TRUE AS river_monitored,
    TRUE AS weather_source_available,
    TIMESTAMP '2026-01-01 06:00:00+00' AS weather_ingested_at_utc,
    5.0 AS temperature_2m_mean,
    10.0 AS temperature_2m_max,
    scenarios.temperature_2m_min,
    5.0 AS precipitation_sum_mm,
    10.0 AS wind_speed_10m_max,
    20.0 AS wind_gusts_10m_max,
    0 AS weather_code_max,
    24 AS weather_hour_count,
    scenarios.temperature_2m_value_count,
    24 AS precipitation_value_count,
    24 AS wind_speed_10m_value_count,
    24 AS wind_gusts_10m_value_count,
    TRUE AS air_quality_source_available,
    TIMESTAMP '2026-01-01 06:00:00+00' AS air_quality_ingested_at_utc,
    10.0 AS european_aqi_mean,
    20.0 AS european_aqi_max,
    2.0 AS pm2_5_mean,
    3.0 AS pm10_mean,
    4.0 AS no2_mean,
    5.0 AS o3_mean,
    24 AS air_quality_hour_count,
    24 AS european_aqi_value_count,
    TRUE AS flood_source_available,
    TIMESTAMP '2026-01-01 06:00:00+00' AS flood_ingested_at_utc,
    20.0 AS river_discharge_m3s
FROM scenarios
