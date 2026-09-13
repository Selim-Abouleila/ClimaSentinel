WITH scenarios AS (
    SELECT 'paris_fr' AS city_id, 1 AS month, 2.3 AS normal_temperature_2m_min
    UNION ALL SELECT 'paris_fr', 2, 4.1
    UNION ALL SELECT 'paris_fr', 3, 1.2
    UNION ALL SELECT 'paris_fr', 4, 3.7
    UNION ALL SELECT 'negative_normal', 1, -2.3
    UNION ALL SELECT 'missing_min', 1, 2.3
    -- Paris in May is intentionally absent to exercise the LEFT JOIN gap.
    UNION ALL SELECT 'partial_day', 1, 2.3
    UNION ALL SELECT 'empty_day', 1, 2.3
    UNION ALL SELECT 'missing_count', 1, 2.3
    UNION ALL SELECT 'nan_min', 1, 2.3
    UNION ALL SELECT 'positive_inf_min', 1, 2.3
    UNION ALL SELECT 'negative_inf_min', 1, 2.3
    UNION ALL SELECT 'nan_normal', 1, CAST('NaN' AS FLOAT64)
    UNION ALL SELECT 'positive_inf_normal', 1, CAST('+inf' AS FLOAT64)
    UNION ALL SELECT 'negative_inf_normal', 1, CAST('-inf' AS FLOAT64)
    UNION ALL SELECT 'rounding_score', 1, 2.3
    UNION ALL SELECT 'near_cap', 1, 2.3
    UNION ALL SELECT 'at_cap', 1, 2.3
    UNION ALL SELECT 'above_cap', 1, 2.3
    UNION ALL SELECT 'very_large_anomaly', 1, 2.3
    UNION ALL SELECT 'negative_normal_equal', 1, -10.0
    UNION ALL SELECT 'positive_min', 1, 20.0
    UNION ALL SELECT 'partial_single', 1, 2.3
    UNION ALL SELECT 'partial_half', 1, 2.3
    UNION ALL SELECT 'negative_count', 1, 2.3
    UNION ALL SELECT 'excessive_count', 1, 2.3
    UNION ALL SELECT 'partial_missing_min', 1, 2.3
    UNION ALL SELECT 'partial_nan_normal', 1, CAST('NaN' AS FLOAT64)
    UNION ALL SELECT 'not_monitored', 1, 2.3
    UNION ALL SELECT 'not_monitored_partial', 1, 2.3
    UNION ALL SELECT 'missing_monitoring', 1, 2.3
    UNION ALL SELECT 'monotonic_2', 1, 2.3
    UNION ALL SELECT 'monotonic_5', 1, 2.3
    UNION ALL SELECT 'monotonic_10', 1, 2.3
)

SELECT
    city_id,
    month,
    5.0 AS normal_temperature_2m_mean,
    10.0 AS normal_temperature_2m_max,
    normal_temperature_2m_min,
    2.0 AS normal_daily_precipitation_mm,
    15.0 AS normal_wind_speed_10m_max
FROM scenarios
