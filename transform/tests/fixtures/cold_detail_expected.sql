-- Literal selected rows: do not repeat the model's window or ranking query.
-- SQL-format expectations include all 59 detail output columns.
WITH expected AS (
    SELECT 'tomorrow_higher' AS city_id, 1 AS day_offset,
        40.0 AS current_tipping_score, 15.0 AS cold_score,
        'available' AS cold_status, TRUE AS cold_monitored,
        TRUE AS cold_available, 1.0 AS cold_coverage,
        2.0 AS temperature_2m_min, 5.0 AS normal_temperature_2m_min,
        3.0 AS cold_anomaly_c
    UNION ALL SELECT 'today_higher', 0, 60.0, 5.0, 'available', TRUE, TRUE, 1.0, 2.0, 3.0, 1.0
    UNION ALL SELECT 'tied_global', 0, 30.0, 10.0, 'available', TRUE, TRUE, 1.0, 0.0, 2.0, 2.0
    UNION ALL SELECT 'partial_selected', 0, 55.0, CAST(NULL AS FLOAT64), 'unavailable', TRUE, FALSE, 0.958, -4.0, 3.0, CAST(NULL AS FLOAT64)
    UNION ALL SELECT 'unmonitored_selected', 1, 45.0, CAST(NULL AS FLOAT64), 'not_monitored', FALSE, FALSE, CAST(NULL AS FLOAT64), -8.0, 4.0, 12.0
    UNION ALL SELECT 'zero_selected', 0, 40.0, 0.0, 'available', TRUE, TRUE, 1.0, 5.0, 4.0, 0.0
    UNION ALL SELECT 'global_unavailable', 0, CAST(NULL AS FLOAT64), 20.0, 'available', TRUE, TRUE, 1.0, 0.0, 4.0, 4.0
    UNION ALL SELECT 'outside_window', 1, 20.0, 20.0, 'available', TRUE, TRUE, 1.0, -1.0, 3.0, 4.0
)

SELECT
    'cold-detail-fixture' AS operational_ingestion_run_id,
    TIMESTAMP '2026-01-01 06:00:00+00' AS operational_ingested_at_utc,
    TRUE AS run_has_weather_source,
    current_tipping_score IS NOT NULL AS run_has_air_quality_source,
    current_tipping_score IS NOT NULL AS run_has_flood_source,
    FALSE AS run_has_historical_weather_source,
    IF(current_tipping_score IS NOT NULL, 3, 1) AS run_source_count,
    city_id,
    DATE_ADD(CURRENT_DATE('UTC'), INTERVAL day_offset DAY) AS score_date,
    current_tipping_score,
    IF(current_tipping_score IS NOT NULL, 'Rain', 'Unavailable') AS current_primary_driver,
    current_tipping_score IS NOT NULL AS current_score_available,
    5 AS monitored_factor_count,
    IF(current_tipping_score IS NOT NULL, 4, 0) AS available_factor_count,
    IF(current_tipping_score IS NOT NULL, 0.8, 0.0) AS overall_coverage,
    TRUE AS weather_source_available,
    TIMESTAMP '2026-01-01 06:00:00+00' AS weather_ingested_at_utc,
    current_tipping_score IS NOT NULL AS air_quality_source_available,
    IF(current_tipping_score IS NOT NULL, TIMESTAMP '2026-01-01 06:00:00+00', CAST(NULL AS TIMESTAMP)) AS air_quality_ingested_at_utc,
    current_tipping_score IS NOT NULL AS flood_source_available,
    IF(current_tipping_score IS NOT NULL, TIMESTAMP '2026-01-01 06:00:00+00', CAST(NULL AS TIMESTAMP)) AS flood_ingested_at_utc,
    CAST(NULL AS FLOAT64) AS heat_score,
    'unavailable' AS heat_status,
    TRUE AS heat_monitored,
    FALSE AS heat_available,
    0.0 AS heat_coverage,
    cold_score,
    cold_status,
    cold_monitored,
    cold_available,
    cold_coverage,
    IF(current_tipping_score IS NOT NULL, 0.0, CAST(NULL AS FLOAT64)) AS wind_score,
    IF(current_tipping_score IS NOT NULL, 'available', 'unavailable') AS wind_status,
    TRUE AS wind_monitored,
    current_tipping_score IS NOT NULL AS wind_available,
    IF(current_tipping_score IS NOT NULL, 1.0, 0.0) AS wind_coverage,
    current_tipping_score AS rain_score,
    IF(current_tipping_score IS NOT NULL, 'available', 'unavailable') AS rain_status,
    TRUE AS rain_monitored,
    current_tipping_score IS NOT NULL AS rain_available,
    IF(current_tipping_score IS NOT NULL, 1.0, 0.0) AS rain_coverage,
    IF(current_tipping_score IS NOT NULL, 0.0, CAST(NULL AS FLOAT64)) AS air_score,
    IF(current_tipping_score IS NOT NULL, 'available', 'unavailable') AS air_status,
    TRUE AS air_monitored,
    current_tipping_score IS NOT NULL AS air_available,
    IF(current_tipping_score IS NOT NULL, 1.0, 0.0) AS air_coverage,
    IF(current_tipping_score IS NOT NULL, 0.0, CAST(NULL AS FLOAT64)) AS river_score,
    IF(current_tipping_score IS NOT NULL, 'available', 'unavailable') AS river_status,
    TRUE AS river_monitored,
    current_tipping_score IS NOT NULL AS river_available,
    IF(current_tipping_score IS NOT NULL, 1.0, 0.0) AS river_coverage,
    10.0 AS temperature_2m_max,
    temperature_2m_min,
    normal_temperature_2m_min,
    cold_anomaly_c,
    IF(current_tipping_score IS NOT NULL, 20.0, CAST(NULL AS FLOAT64)) AS wind_gusts_10m_max,
    IF(current_tipping_score IS NOT NULL, current_tipping_score / 2.0, CAST(NULL AS FLOAT64)) AS precipitation_sum_mm,
    IF(current_tipping_score IS NOT NULL, 20.0, CAST(NULL AS FLOAT64)) AS european_aqi_max,
    IF(current_tipping_score IS NOT NULL, 20.0, CAST(NULL AS FLOAT64)) AS river_discharge_m3s
FROM expected
