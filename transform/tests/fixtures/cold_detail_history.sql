-- Complete history schema: SQL-format dbt fixtures must provide every column.
-- The selected date continues to follow the existing five-factor global score.
-- Cold values deliberately disagree with that ordering in several scenarios.
WITH scenarios AS (
    SELECT 'tomorrow_higher' AS city_id, 0 AS day_offset,
        10.0 AS global_tipping_score, 100.0 AS cold_score,
        'available' AS cold_status, TRUE AS cold_monitored,
        TRUE AS cold_available, 1.0 AS cold_coverage,
        -16.0 AS temperature_2m_min, 4.0 AS normal_temperature_2m_min,
        20.0 AS cold_anomaly_c
    UNION ALL SELECT 'tomorrow_higher', 1, 40.0, 15.0, 'available', TRUE, TRUE, 1.0, 2.0, 5.0, 3.0
    UNION ALL SELECT 'today_higher', 0, 60.0, 5.0, 'available', TRUE, TRUE, 1.0, 2.0, 3.0, 1.0
    UNION ALL SELECT 'today_higher', 1, 20.0, 90.0, 'available', TRUE, TRUE, 1.0, -14.0, 4.0, 18.0
    UNION ALL SELECT 'tied_global', 0, 30.0, 10.0, 'available', TRUE, TRUE, 1.0, 0.0, 2.0, 2.0
    UNION ALL SELECT 'tied_global', 1, 30.0, 100.0, 'available', TRUE, TRUE, 1.0, -17.0, 3.0, 20.0
    UNION ALL SELECT 'partial_selected', 0, 55.0, CAST(NULL AS FLOAT64), 'unavailable', TRUE, FALSE, 0.958, -4.0, 3.0, CAST(NULL AS FLOAT64)
    UNION ALL SELECT 'partial_selected', 1, 20.0, 30.0, 'available', TRUE, TRUE, 1.0, -2.0, 4.0, 6.0
    UNION ALL SELECT 'unmonitored_selected', 0, 15.0, 35.0, 'available', TRUE, TRUE, 1.0, -3.0, 4.0, 7.0
    UNION ALL SELECT 'unmonitored_selected', 1, 45.0, CAST(NULL AS FLOAT64), 'not_monitored', FALSE, FALSE, CAST(NULL AS FLOAT64), -8.0, 4.0, 12.0
    UNION ALL SELECT 'zero_selected', 0, 40.0, 0.0, 'available', TRUE, TRUE, 1.0, 5.0, 4.0, 0.0
    UNION ALL SELECT 'zero_selected', 1, 30.0, 25.0, 'available', TRUE, TRUE, 1.0, 0.0, 5.0, 5.0
    UNION ALL SELECT 'global_unavailable', 0, CAST(NULL AS FLOAT64), 20.0, 'available', TRUE, TRUE, 1.0, 0.0, 4.0, 4.0
    UNION ALL SELECT 'global_unavailable', 1, CAST(NULL AS FLOAT64), 75.0, 'available', TRUE, TRUE, 1.0, -10.0, 5.0, 15.0
    UNION ALL SELECT 'outside_window', -1, 99.0, 100.0, 'available', TRUE, TRUE, 1.0, -20.0, 1.0, 21.0
    UNION ALL SELECT 'outside_window', 0, 10.0, 10.0, 'available', TRUE, TRUE, 1.0, 0.0, 2.0, 2.0
    UNION ALL SELECT 'outside_window', 1, 20.0, 20.0, 'available', TRUE, TRUE, 1.0, -1.0, 3.0, 4.0
    UNION ALL SELECT 'outside_window', 2, 100.0, 100.0, 'available', TRUE, TRUE, 1.0, -20.0, 4.0, 24.0
)

SELECT
    'cold-detail-fixture' AS operational_ingestion_run_id,
    TIMESTAMP '2026-01-01 06:00:00+00' AS operational_ingested_at_utc,
    TRUE AS run_has_weather_source,
    global_tipping_score IS NOT NULL AS run_has_air_quality_source,
    global_tipping_score IS NOT NULL AS run_has_flood_source,
    FALSE AS run_has_historical_weather_source,
    IF(global_tipping_score IS NOT NULL, 3, 1) AS run_source_count,
    city_id,
    DATE_ADD(CURRENT_DATE('UTC'), INTERVAL day_offset DAY) AS date,
    TRUE AS weather_source_available,
    TIMESTAMP '2026-01-01 06:00:00+00' AS weather_ingested_at_utc,
    global_tipping_score IS NOT NULL AS air_quality_source_available,
    IF(global_tipping_score IS NOT NULL, TIMESTAMP '2026-01-01 06:00:00+00', CAST(NULL AS TIMESTAMP)) AS air_quality_ingested_at_utc,
    global_tipping_score IS NOT NULL AS flood_source_available,
    IF(global_tipping_score IS NOT NULL, TIMESTAMP '2026-01-01 06:00:00+00', CAST(NULL AS TIMESTAMP)) AS flood_ingested_at_utc,
    10.0 AS temperature_2m_max,
    temperature_2m_min,
    normal_temperature_2m_min,
    cold_anomaly_c,
    IF(global_tipping_score IS NOT NULL, global_tipping_score / 2.0, CAST(NULL AS FLOAT64)) AS precipitation_sum_mm,
    IF(global_tipping_score IS NOT NULL, 20.0, CAST(NULL AS FLOAT64)) AS wind_gusts_10m_max,
    IF(global_tipping_score IS NOT NULL, 20.0, CAST(NULL AS FLOAT64)) AS european_aqi_max,
    IF(global_tipping_score IS NOT NULL, 20.0, CAST(NULL AS FLOAT64)) AS river_discharge_m3s,
    CAST(NULL AS FLOAT64) AS heat_score,
    cold_score,
    IF(global_tipping_score IS NOT NULL, 0.0, CAST(NULL AS FLOAT64)) AS wind_score,
    global_tipping_score AS rain_score,
    IF(global_tipping_score IS NOT NULL, 0.0, CAST(NULL AS FLOAT64)) AS air_score,
    IF(global_tipping_score IS NOT NULL, 0.0, CAST(NULL AS FLOAT64)) AS river_score,
    'unavailable' AS heat_status,
    TRUE AS heat_monitored,
    FALSE AS heat_available,
    0.0 AS heat_coverage,
    cold_status,
    cold_monitored,
    cold_available,
    cold_coverage,
    IF(global_tipping_score IS NOT NULL, 'available', 'unavailable') AS wind_status,
    TRUE AS wind_monitored,
    global_tipping_score IS NOT NULL AS wind_available,
    IF(global_tipping_score IS NOT NULL, 1.0, 0.0) AS wind_coverage,
    IF(global_tipping_score IS NOT NULL, 'available', 'unavailable') AS rain_status,
    TRUE AS rain_monitored,
    global_tipping_score IS NOT NULL AS rain_available,
    IF(global_tipping_score IS NOT NULL, 1.0, 0.0) AS rain_coverage,
    IF(global_tipping_score IS NOT NULL, 'available', 'unavailable') AS air_status,
    TRUE AS air_monitored,
    global_tipping_score IS NOT NULL AS air_available,
    IF(global_tipping_score IS NOT NULL, 1.0, 0.0) AS air_coverage,
    IF(global_tipping_score IS NOT NULL, 'available', 'unavailable') AS river_status,
    TRUE AS river_monitored,
    global_tipping_score IS NOT NULL AS river_available,
    IF(global_tipping_score IS NOT NULL, 1.0, 0.0) AS river_coverage,
    5 AS monitored_factor_count,
    IF(global_tipping_score IS NOT NULL, 4, 0) AS available_factor_count,
    IF(global_tipping_score IS NOT NULL, 0.8, 0.0) AS overall_coverage,
    global_tipping_score IS NOT NULL AS global_score_available,
    global_tipping_score,
    IF(global_tipping_score IS NOT NULL, 'Rain', 'Unavailable') AS primary_driver,
    FALSE AS cold_in_global_score
FROM scenarios
