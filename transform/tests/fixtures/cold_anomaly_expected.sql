-- Expected anomalies are literal examples, independent of the model formula.
WITH expected AS (
    SELECT 'paris_fr' AS city_id, DATE '2026-01-02' AS date,
        -5.0 AS temperature_2m_min, 2.3 AS normal_temperature_2m_min,
        7.3 AS cold_anomaly_c, FALSE AS heat_monitored
    UNION ALL SELECT 'paris_fr', DATE '2026-02-02', 4.1, 4.1, 0.0, TRUE
    UNION ALL SELECT 'paris_fr', DATE '2026-03-02', 5.0, 1.2, 0.0, TRUE
    UNION ALL SELECT 'paris_fr', DATE '2026-04-02', 0.0, 3.7, 3.7, TRUE
    UNION ALL SELECT 'negative_normal', DATE '2026-01-02', -25.236, -2.3, 22.94, TRUE
    UNION ALL SELECT 'missing_min', DATE '2026-01-02', CAST(NULL AS FLOAT64), 2.3, CAST(NULL AS FLOAT64), TRUE
    UNION ALL SELECT 'paris_fr', DATE '2026-05-02', -5.0, CAST(NULL AS FLOAT64), CAST(NULL AS FLOAT64), TRUE
    UNION ALL SELECT 'partial_day', DATE '2026-01-02', -5.0, 2.3, CAST(NULL AS FLOAT64), TRUE
    UNION ALL SELECT 'empty_day', DATE '2026-01-02', -5.0, 2.3, CAST(NULL AS FLOAT64), TRUE
    UNION ALL SELECT 'missing_count', DATE '2026-01-02', -5.0, 2.3, CAST(NULL AS FLOAT64), TRUE
    UNION ALL SELECT 'nan_min', DATE '2026-01-02', CAST('NaN' AS FLOAT64), 2.3, CAST(NULL AS FLOAT64), TRUE
    UNION ALL SELECT 'positive_inf_min', DATE '2026-01-02', CAST('+inf' AS FLOAT64), 2.3, CAST(NULL AS FLOAT64), TRUE
    UNION ALL SELECT 'negative_inf_min', DATE '2026-01-02', CAST('-inf' AS FLOAT64), 2.3, CAST(NULL AS FLOAT64), TRUE
    UNION ALL SELECT 'nan_normal', DATE '2026-01-02', -5.0, CAST('NaN' AS FLOAT64), CAST(NULL AS FLOAT64), TRUE
    UNION ALL SELECT 'positive_inf_normal', DATE '2026-01-02', -5.0, CAST('+inf' AS FLOAT64), CAST(NULL AS FLOAT64), TRUE
    UNION ALL SELECT 'negative_inf_normal', DATE '2026-01-02', -5.0, CAST('-inf' AS FLOAT64), CAST(NULL AS FLOAT64), TRUE
)

SELECT
    city_id,
    date,
    temperature_2m_min,
    normal_temperature_2m_min,
    cold_anomaly_c,
    heat_monitored,
    CAST(NULL AS FLOAT64) AS heat_score,
    FALSE AS heat_available,
    IF(heat_monitored, 'unavailable', 'not_monitored') AS heat_status,
    0.0 AS wind_score,
    10.0 AS rain_score,
    0.0 AS air_score,
    0.0 AS river_score,
    10.0 AS global_tipping_score,
    TRUE AS global_score_available,
    'Rain' AS primary_driver,
    IF(heat_monitored, 5, 4) AS monitored_factor_count,
    4 AS available_factor_count,
    IF(heat_monitored, 0.8, 1.0) AS overall_coverage
FROM expected
