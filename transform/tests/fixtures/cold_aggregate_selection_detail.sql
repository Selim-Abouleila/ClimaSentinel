-- Independently listed selected rows; no window, MAX or ranking query here.
-- All 60 detail columns are expected, including source and factor metadata.
-- The earliest date wins ties, including when neither date has an available score.
WITH expected AS (
    SELECT 'cold_today' AS city_id,
        0 AS day_offset,
        90.0 AS global_tipping_score,
        'Cold' AS primary_driver,
        0.0 AS heat_score,
        90.0 AS cold_score,
        20.0 AS wind_score,
        0.0 AS rain_score,
        0.0 AS air_score,
        0.0 AS river_score,
        'available' AS cold_status,
        TRUE AS cold_monitored,
        1.0 AS cold_coverage,
        10.0 AS temperature_2m_max,
        -14.0 AS temperature_2m_min,
        4.0 AS normal_temperature_2m_min,
        18.0 AS cold_anomaly_c,
        6 AS monitored_factor_count,
        6 AS available_factor_count,
        1.0 AS overall_coverage,
        TRUE AS weather_source_available
    UNION ALL SELECT 'cold_tomorrow', 1, 90.0, 'Cold', 0.0, 90.0, 30.0, 0.0, 0.0, 0.0, 'available', TRUE, 1.0, 10.0, -14.0, 4.0, 18.0, 6, 6, 1.0, TRUE
    UNION ALL SELECT 'earlier_tie', 0, 80.0, 'Rain', 0.0, 80.0, 0.0, 80.0, 0.0, 0.0, 'available', TRUE, 1.0, 10.0, -12.0, 4.0, 16.0, 6, 6, 1.0, TRUE
    UNION ALL SELECT 'heat_tie', 0, 70.0, 'Heat', 70.0, 70.0, 70.0, 70.0, 70.0, 70.0, 'available', TRUE, 1.0, 34.0, -10.0, 4.0, 14.0, 6, 6, 1.0, TRUE
    UNION ALL SELECT 'unmonitored_cold', 1, 60.0, 'River/Flood', 0.0, CAST(NULL AS FLOAT64), 0.0, 0.0, 0.0, 60.0, 'not_monitored', FALSE, CAST(NULL AS FLOAT64), 10.0, -20.0, 4.0, 24.0, 5, 5, 1.0, TRUE
    UNION ALL SELECT 'partial_cold', 0, 50.0, 'Rain', CAST(NULL AS FLOAT64), CAST(NULL AS FLOAT64), 10.0, 50.0, 0.0, 0.0, 'unavailable', TRUE, 0.958, 10.0, -4.0, 3.0, CAST(NULL AS FLOAT64), 6, 4, 0.826, TRUE
    UNION ALL SELECT 'missing_cold', 0, 40.0, 'Wind', CAST(NULL AS FLOAT64), CAST(NULL AS FLOAT64), 40.0, 10.0, 0.0, 0.0, 'unavailable', TRUE, 0.0, CAST(NULL AS FLOAT64), CAST(NULL AS FLOAT64), 4.0, CAST(NULL AS FLOAT64), 6, 4, 0.667, TRUE
    UNION ALL SELECT 'air_tie', 0, 35.0, 'Air Quality', 0.0, 35.0, 0.0, 0.0, 35.0, 0.0, 'available', TRUE, 1.0, 10.0, -3.0, 4.0, 7.0, 6, 6, 1.0, TRUE
    UNION ALL SELECT 'outside_window', 1, 30.0, 'Cold', 0.0, 30.0, 0.0, 20.0, 0.0, 0.0, 'available', TRUE, 1.0, 10.0, -2.0, 4.0, 6.0, 6, 6, 1.0, TRUE
    UNION ALL SELECT 'zero_beats_unavailable', 1, 0.0, 'Stable', CAST(NULL AS FLOAT64), 0.0, CAST(NULL AS FLOAT64), CAST(NULL AS FLOAT64), CAST(NULL AS FLOAT64), CAST(NULL AS FLOAT64), 'available', TRUE, 1.0, 10.0, 5.0, 4.0, 0.0, 6, 1, 0.167, TRUE
    UNION ALL SELECT 'both_unavailable', 0, CAST(NULL AS FLOAT64), 'Unavailable', CAST(NULL AS FLOAT64), CAST(NULL AS FLOAT64), CAST(NULL AS FLOAT64), CAST(NULL AS FLOAT64), CAST(NULL AS FLOAT64), CAST(NULL AS FLOAT64), 'unavailable', TRUE, 0.0, CAST(NULL AS FLOAT64), CAST(NULL AS FLOAT64), 4.0, CAST(NULL AS FLOAT64), 6, 0, 0.0, FALSE
)

SELECT
    'cold-aggregate-selection-fixture' AS operational_ingestion_run_id,
    TIMESTAMP '2026-01-01 06:00:00+00' AS operational_ingested_at_utc,
    TRUE AS run_has_weather_source,
    TRUE AS run_has_air_quality_source,
    TRUE AS run_has_flood_source,
    FALSE AS run_has_historical_weather_source,
    3 AS run_source_count,
    city_id,
    DATE_ADD(CURRENT_DATE('UTC'), INTERVAL day_offset DAY) AS score_date,
    global_tipping_score AS current_tipping_score,
    primary_driver AS current_primary_driver,
    global_tipping_score IS NOT NULL AS current_score_available,
    monitored_factor_count,
    available_factor_count,
    overall_coverage,
    weather_source_available,
    IF(weather_source_available, TIMESTAMP '2026-01-01 06:00:00+00', CAST(NULL AS TIMESTAMP)) AS weather_ingested_at_utc,
    air_score IS NOT NULL AS air_quality_source_available,
    IF(air_score IS NOT NULL, TIMESTAMP '2026-01-01 06:00:00+00', CAST(NULL AS TIMESTAMP)) AS air_quality_ingested_at_utc,
    river_score IS NOT NULL AS flood_source_available,
    IF(river_score IS NOT NULL, TIMESTAMP '2026-01-01 06:00:00+00', CAST(NULL AS TIMESTAMP)) AS flood_ingested_at_utc,
    heat_score,
    IF(heat_score IS NOT NULL, 'available', 'unavailable') AS heat_status,
    TRUE AS heat_monitored,
    heat_score IS NOT NULL AS heat_available,
    IF(heat_score IS NOT NULL, 1.0, 0.0) AS heat_coverage,
    cold_score,
    cold_status,
    cold_monitored,
    cold_score IS NOT NULL AS cold_available,
    cold_coverage,
    wind_score,
    IF(wind_score IS NOT NULL, 'available', 'unavailable') AS wind_status,
    TRUE AS wind_monitored,
    wind_score IS NOT NULL AS wind_available,
    IF(wind_score IS NOT NULL, 1.0, 0.0) AS wind_coverage,
    rain_score,
    IF(rain_score IS NOT NULL, 'available', 'unavailable') AS rain_status,
    TRUE AS rain_monitored,
    rain_score IS NOT NULL AS rain_available,
    IF(rain_score IS NOT NULL, 1.0, 0.0) AS rain_coverage,
    air_score,
    IF(air_score IS NOT NULL, 'available', 'unavailable') AS air_status,
    TRUE AS air_monitored,
    air_score IS NOT NULL AS air_available,
    IF(air_score IS NOT NULL, 1.0, 0.0) AS air_coverage,
    river_score,
    IF(river_score IS NOT NULL, 'available', 'unavailable') AS river_status,
    TRUE AS river_monitored,
    river_score IS NOT NULL AS river_available,
    IF(river_score IS NOT NULL, 1.0, 0.0) AS river_coverage,
    temperature_2m_max,
    temperature_2m_min,
    normal_temperature_2m_min,
    cold_anomaly_c,
    wind_score / 2.5 + 40.0 AS wind_gusts_10m_max,
    rain_score / 2.0 AS precipitation_sum_mm,
    air_score / 1.67 + 40.0 AS european_aqi_max,
    IF(river_score IS NULL, CAST(NULL AS FLOAT64), IF(river_score > 0.0, 80.0, 20.0)) AS river_discharge_m3s,
    TRUE AS cold_in_global_score
FROM expected
