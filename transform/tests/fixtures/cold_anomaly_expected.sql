-- Expected anomalies, Cold scores and coverage are literal contract examples.
-- SQL-format expectations must supply every model output column: dbt selects
-- the complete actual schema from this fixture when building its comparison.
WITH expected AS (
    SELECT 'paris_fr' AS city_id, DATE '2026-01-02' AS date,
        -5.0 AS temperature_2m_min, 2.3 AS normal_temperature_2m_min,
        7.3 AS cold_anomaly_c, FALSE AS heat_monitored, TRUE AS cold_monitored,
        36.5 AS cold_score, 'available' AS cold_status,
        TRUE AS cold_available, 1.0 AS cold_coverage
    UNION ALL SELECT 'paris_fr', DATE '2026-02-02', 4.1, 4.1, 0.0, TRUE, TRUE, 0.0, 'available', TRUE, 1.0
    UNION ALL SELECT 'paris_fr', DATE '2026-03-02', 5.0, 1.2, 0.0, TRUE, TRUE, 0.0, 'available', TRUE, 1.0
    UNION ALL SELECT 'paris_fr', DATE '2026-04-02', 0.0, 3.7, 3.7, TRUE, TRUE, 18.5, 'available', TRUE, 1.0
    UNION ALL SELECT 'negative_normal', DATE '2026-01-02', -25.236, -2.3, 22.94, TRUE, TRUE, 100.0, 'available', TRUE, 1.0
    UNION ALL SELECT 'missing_min', DATE '2026-01-02', CAST(NULL AS FLOAT64), 2.3, NULL, TRUE, TRUE, NULL, 'unavailable', FALSE, 0.0
    UNION ALL SELECT 'paris_fr', DATE '2026-05-02', -5.0, CAST(NULL AS FLOAT64), NULL, TRUE, TRUE, NULL, 'unavailable', FALSE, 0.0
    UNION ALL SELECT 'partial_day', DATE '2026-01-02', -5.0, 2.3, NULL, TRUE, TRUE, NULL, 'unavailable', FALSE, 0.958
    UNION ALL SELECT 'empty_day', DATE '2026-01-02', -5.0, 2.3, NULL, TRUE, TRUE, NULL, 'unavailable', FALSE, 0.0
    UNION ALL SELECT 'missing_count', DATE '2026-01-02', -5.0, 2.3, NULL, TRUE, TRUE, NULL, 'unavailable', FALSE, 0.0
    UNION ALL SELECT 'nan_min', DATE '2026-01-02', CAST('NaN' AS FLOAT64), 2.3, NULL, TRUE, TRUE, NULL, 'unavailable', FALSE, 0.0
    UNION ALL SELECT 'positive_inf_min', DATE '2026-01-02', CAST('+inf' AS FLOAT64), 2.3, NULL, TRUE, TRUE, NULL, 'unavailable', FALSE, 0.0
    UNION ALL SELECT 'negative_inf_min', DATE '2026-01-02', CAST('-inf' AS FLOAT64), 2.3, NULL, TRUE, TRUE, NULL, 'unavailable', FALSE, 0.0
    UNION ALL SELECT 'nan_normal', DATE '2026-01-02', -5.0, CAST('NaN' AS FLOAT64), NULL, TRUE, TRUE, NULL, 'unavailable', FALSE, 0.0
    UNION ALL SELECT 'positive_inf_normal', DATE '2026-01-02', -5.0, CAST('+inf' AS FLOAT64), NULL, TRUE, TRUE, NULL, 'unavailable', FALSE, 0.0
    UNION ALL SELECT 'negative_inf_normal', DATE '2026-01-02', -5.0, CAST('-inf' AS FLOAT64), NULL, TRUE, TRUE, NULL, 'unavailable', FALSE, 0.0
    UNION ALL SELECT 'rounding_score', DATE '2026-01-02', 1.07, 2.3, 1.23, TRUE, TRUE, 6.2, 'available', TRUE, 1.0
    UNION ALL SELECT 'near_cap', DATE '2026-01-02', -17.69, 2.3, 19.99, TRUE, TRUE, 100.0, 'available', TRUE, 1.0
    UNION ALL SELECT 'at_cap', DATE '2026-01-02', -17.70, 2.3, 20.0, TRUE, TRUE, 100.0, 'available', TRUE, 1.0
    UNION ALL SELECT 'above_cap', DATE '2026-01-02', -22.70, 2.3, 25.0, TRUE, TRUE, 100.0, 'available', TRUE, 1.0
    UNION ALL SELECT 'very_large_anomaly', DATE '2026-01-02', -1e100, 2.3, 1e100, TRUE, TRUE, 100.0, 'available', TRUE, 1.0
    UNION ALL SELECT 'negative_normal_equal', DATE '2026-01-02', -10.0, -10.0, 0.0, TRUE, TRUE, 0.0, 'available', TRUE, 1.0
    UNION ALL SELECT 'positive_min', DATE '2026-01-02', 12.0, 20.0, 8.0, TRUE, TRUE, 40.0, 'available', TRUE, 1.0
    UNION ALL SELECT 'partial_single', DATE '2026-01-02', -5.0, 2.3, NULL, TRUE, TRUE, NULL, 'unavailable', FALSE, 0.042
    UNION ALL SELECT 'partial_half', DATE '2026-01-02', -5.0, 2.3, NULL, TRUE, TRUE, NULL, 'unavailable', FALSE, 0.5
    UNION ALL SELECT 'negative_count', DATE '2026-01-02', -5.0, 2.3, NULL, FALSE, TRUE, NULL, 'unavailable', FALSE, 0.0
    UNION ALL SELECT 'excessive_count', DATE '2026-01-02', -5.0, 2.3, NULL, TRUE, TRUE, NULL, 'unavailable', FALSE, 0.0
    UNION ALL SELECT 'partial_missing_min', DATE '2026-01-02', CAST(NULL AS FLOAT64), 2.3, NULL, TRUE, TRUE, NULL, 'unavailable', FALSE, 0.0
    UNION ALL SELECT 'partial_nan_normal', DATE '2026-01-02', -5.0, CAST('NaN' AS FLOAT64), NULL, TRUE, TRUE, NULL, 'unavailable', FALSE, 0.0
    UNION ALL SELECT 'not_monitored', DATE '2026-01-02', -5.0, 2.3, 7.3, TRUE, FALSE, NULL, 'not_monitored', FALSE, CAST(NULL AS FLOAT64)
    UNION ALL SELECT 'not_monitored_partial', DATE '2026-01-02', -5.0, 2.3, NULL, TRUE, FALSE, NULL, 'not_monitored', FALSE, CAST(NULL AS FLOAT64)
    UNION ALL SELECT 'missing_monitoring', DATE '2026-01-02', -5.0, 2.3, 7.3, TRUE, CAST(NULL AS BOOL), NULL, 'unavailable', FALSE, 0.0
    UNION ALL SELECT 'monotonic_2', DATE '2026-01-02', 0.3, 2.3, 2.0, TRUE, TRUE, 10.0, 'available', TRUE, 1.0
    UNION ALL SELECT 'monotonic_5', DATE '2026-01-02', -2.7, 2.3, 5.0, TRUE, TRUE, 25.0, 'available', TRUE, 1.0
    UNION ALL SELECT 'monotonic_10', DATE '2026-01-02', -7.7, 2.3, 10.0, TRUE, TRUE, 50.0, 'available', TRUE, 1.0
)

SELECT
    'cold-anomaly-fixture' AS operational_ingestion_run_id,
    TIMESTAMP '2026-01-01 06:00:00+00' AS operational_ingested_at_utc,
    TRUE AS run_has_weather_source,
    TRUE AS run_has_air_quality_source,
    TRUE AS run_has_flood_source,
    FALSE AS run_has_historical_weather_source,
    3 AS run_source_count,
    city_id,
    date,
    TRUE AS weather_source_available,
    TIMESTAMP '2026-01-01 06:00:00+00' AS weather_ingested_at_utc,
    TRUE AS air_quality_source_available,
    TIMESTAMP '2026-01-01 06:00:00+00' AS air_quality_ingested_at_utc,
    TRUE AS flood_source_available,
    TIMESTAMP '2026-01-01 06:00:00+00' AS flood_ingested_at_utc,
    10.0 AS temperature_2m_max,
    temperature_2m_min,
    normal_temperature_2m_min,
    cold_anomaly_c,
    5.0 AS precipitation_sum_mm,
    20.0 AS wind_gusts_10m_max,
    20.0 AS european_aqi_max,
    20.0 AS river_discharge_m3s,
    CAST(NULL AS FLOAT64) AS heat_score,
    cold_score,
    0.0 AS wind_score,
    10.0 AS rain_score,
    0.0 AS air_score,
    0.0 AS river_score,
    IF(heat_monitored, 'unavailable', 'not_monitored') AS heat_status,
    heat_monitored,
    FALSE AS heat_available,
    IF(heat_monitored, 0.0, CAST(NULL AS FLOAT64)) AS heat_coverage,
    cold_status,
    cold_monitored,
    cold_available,
    cold_coverage,
    'available' AS wind_status,
    TRUE AS wind_monitored,
    TRUE AS wind_available,
    1.0 AS wind_coverage,
    'available' AS rain_status,
    TRUE AS rain_monitored,
    TRUE AS rain_available,
    1.0 AS rain_coverage,
    'available' AS air_status,
    TRUE AS air_monitored,
    TRUE AS air_available,
    1.0 AS air_coverage,
    'available' AS river_status,
    TRUE AS river_monitored,
    TRUE AS river_available,
    1.0 AS river_coverage,
    IF(heat_monitored, 5, 4) AS monitored_factor_count,
    4 AS available_factor_count,
    IF(heat_monitored, 0.8, 1.0) AS overall_coverage,
    TRUE AS global_score_available,
    10.0 AS global_tipping_score,
    'Rain' AS primary_driver
FROM expected
