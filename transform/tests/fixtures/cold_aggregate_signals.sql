-- Four cities include a next-day support row for the existing Heat/River
-- velocity rules. Every other city has one day; Cold needs no following day.
-- A source can exist while individual city/day fields are missing.
WITH scenarios AS (
    SELECT 'cold_max' AS city_id, DATE '2026-01-02' AS date, 10.0 AS temperature_2m_max, -10.0 AS temperature_2m_min, 24 AS temperature_2m_value_count, TRUE AS monitored, TRUE AS cold_monitored, 20.0 AS wind_gusts_10m_max, 24 AS wind_gusts_10m_value_count, 5.0 AS precipitation_sum_mm, 24 AS precipitation_value_count, 20.0 AS european_aqi_max, 24 AS european_aqi_value_count, 20.0 AS river_discharge_m3s
    UNION ALL SELECT 'cold_max', DATE '2026-01-03', 10.0, -10.0, 24, TRUE, TRUE, 20.0, 24, 5.0, 24, 20.0, 24, 20.0
    UNION ALL SELECT 'tie_heat', DATE '2026-01-02', 20.0, -10.0, 24, TRUE, TRUE, 20.0, 24, 5.0, 24, 20.0, 24, 20.0
    UNION ALL SELECT 'tie_heat', DATE '2026-01-03', 20.0, -10.0, 24, TRUE, TRUE, 20.0, 24, 5.0, 24, 20.0, 24, 20.0
    UNION ALL SELECT 'tie_river', DATE '2026-01-02', 10.0, -10.0, 24, TRUE, TRUE, 20.0, 24, 5.0, 24, 20.0, 24, 100.0
    UNION ALL SELECT 'tie_river', DATE '2026-01-03', 10.0, -10.0, 24, TRUE, TRUE, 20.0, 24, 5.0, 24, 20.0, 24, 125.0
    UNION ALL SELECT 'tie_wind', DATE '2026-01-02', 10.0, -10.0, 24, TRUE, TRUE, 60.0, 24, 5.0, 24, 20.0, 24, 20.0
    UNION ALL SELECT 'tie_rain', DATE '2026-01-02', 10.0, -10.0, 24, TRUE, TRUE, 20.0, 24, 25.0, 24, 20.0, 24, 20.0
    UNION ALL SELECT 'tie_air', DATE '2026-01-02', 10.0, -20.0, 24, TRUE, TRUE, 20.0, 24, 5.0, 24, 100.0, 24, 20.0
    UNION ALL SELECT 'zero_cold', DATE '2026-01-02', 10.0, 0.0, 24, TRUE, TRUE, 20.0, 24, 0.0, 24, 20.0, 24, 20.0
    UNION ALL SELECT 'cold_only_available', DATE '2026-01-02', CAST(NULL AS FLOAT64), -10.0, 24, TRUE, TRUE, CAST(NULL AS FLOAT64), 0, CAST(NULL AS FLOAT64), 0, CAST(NULL AS FLOAT64), 0, CAST(NULL AS FLOAT64)
    UNION ALL SELECT 'all_unavailable', DATE '2026-01-02', CAST(NULL AS FLOAT64), CAST(NULL AS FLOAT64), 0, TRUE, TRUE, CAST(NULL AS FLOAT64), 0, CAST(NULL AS FLOAT64), 0, CAST(NULL AS FLOAT64), 0, CAST(NULL AS FLOAT64)
    UNION ALL SELECT 'cold_not_monitored', DATE '2026-01-02', 10.0, -20.0, 24, TRUE, FALSE, 20.0, 24, 5.0, 24, 20.0, 24, 20.0
    UNION ALL SELECT 'partial_cold', DATE '2026-01-02', 10.0, -10.0, 23, TRUE, TRUE, 20.0, 24, 5.0, 24, 20.0, 24, 20.0
    UNION ALL SELECT 'raw_coverage_rounding', DATE '2026-01-02', 10.0, -10.0, 23, TRUE, TRUE, 20.0, 1, 5.0, 1, 20.0, 3, CAST(NULL AS FLOAT64)
    UNION ALL SELECT 'all_not_monitored', DATE '2026-01-02', 10.0, -10.0, 24, FALSE, FALSE, 20.0, 24, 5.0, 24, 20.0, 24, 20.0
    UNION ALL SELECT 'all_tied', DATE '2026-01-02', 30.0, -20.0, 24, TRUE, TRUE, 80.0, 24, 50.0, 24, 100.0, 24, 100.0
    UNION ALL SELECT 'all_tied', DATE '2026-01-03', 30.0, -20.0, 24, TRUE, TRUE, 80.0, 24, 50.0, 24, 100.0, 24, 150.0
)

SELECT
    'cold-aggregate-fixture' AS operational_ingestion_run_id,
    TIMESTAMP '2026-01-01 06:00:00+00' AS operational_ingested_at_utc,
    TRUE AS run_has_weather_source,
    TRUE AS run_has_air_quality_source,
    TRUE AS run_has_flood_source,
    FALSE AS run_has_historical_weather_source,
    3 AS run_source_count,
    city_id,
    date,
    monitored AS heat_monitored,
    cold_monitored,
    monitored AS wind_monitored,
    monitored AS rain_monitored,
    monitored AS air_monitored,
    monitored AS river_monitored,
    TRUE AS weather_source_available,
    TIMESTAMP '2026-01-01 06:00:00+00' AS weather_ingested_at_utc,
    5.0 AS temperature_2m_mean,
    temperature_2m_max,
    temperature_2m_min,
    precipitation_sum_mm,
    10.0 AS wind_speed_10m_max,
    wind_gusts_10m_max,
    0 AS weather_code_max,
    24 AS weather_hour_count,
    temperature_2m_value_count,
    precipitation_value_count,
    24 AS wind_speed_10m_value_count,
    wind_gusts_10m_value_count,
    TRUE AS air_quality_source_available,
    TIMESTAMP '2026-01-01 06:00:00+00' AS air_quality_ingested_at_utc,
    10.0 AS european_aqi_mean,
    european_aqi_max,
    2.0 AS pm2_5_mean,
    3.0 AS pm10_mean,
    4.0 AS no2_mean,
    5.0 AS o3_mean,
    24 AS air_quality_hour_count,
    european_aqi_value_count,
    TRUE AS flood_source_available,
    TIMESTAMP '2026-01-01 06:00:00+00' AS flood_ingested_at_utc,
    river_discharge_m3s
FROM scenarios
