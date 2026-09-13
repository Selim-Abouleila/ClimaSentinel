WITH cities AS (
    SELECT 'cold_max' AS city_id
    UNION ALL SELECT 'tie_heat'
    UNION ALL SELECT 'tie_river'
    UNION ALL SELECT 'tie_wind'
    UNION ALL SELECT 'tie_rain'
    UNION ALL SELECT 'tie_air'
    UNION ALL SELECT 'zero_cold'
    UNION ALL SELECT 'cold_only_available'
    UNION ALL SELECT 'all_unavailable'
    UNION ALL SELECT 'cold_not_monitored'
    UNION ALL SELECT 'partial_cold'
    UNION ALL SELECT 'raw_coverage_rounding'
    UNION ALL SELECT 'all_not_monitored'
    UNION ALL SELECT 'all_tied'
)

SELECT
    city_id,
    1 AS month,
    5.0 AS normal_temperature_2m_mean,
    10.0 AS normal_temperature_2m_max,
    0.0 AS normal_temperature_2m_min,
    2.0 AS normal_daily_precipitation_mm,
    15.0 AS normal_wind_speed_10m_max
FROM cities
