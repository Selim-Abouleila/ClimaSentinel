-- All scores, factor coverages and aggregate outcomes below are literals.
-- Include support days and all 60 history output columns for dbt's SQL fixture.
-- raw_coverage_rounding averages raw fractions (23 + 1 + 1 + 3) / 24 / 6:
-- 0.194 after rounding. Averaging rounded factor columns would wrongly give 0.195.
WITH expected AS (
    SELECT 'cold_max' AS city_id, DATE '2026-01-02' AS date, 10.0 AS temperature_2m_max, -10.0 AS temperature_2m_min, 5.0 AS precipitation_sum_mm, 20.0 AS wind_gusts_10m_max, 20.0 AS european_aqi_max, 20.0 AS river_discharge_m3s, TRUE AS monitored, TRUE AS cold_monitored, 10.0 AS cold_anomaly_c, 0.0 AS heat_score, 50.0 AS cold_score, 0.0 AS wind_score, 10.0 AS rain_score, 0.0 AS air_score, 0.0 AS river_score, 1.0 AS heat_coverage, 1.0 AS cold_coverage, 1.0 AS wind_coverage, 1.0 AS rain_coverage, 1.0 AS air_coverage, 1.0 AS river_coverage, 6 AS monitored_factor_count, 6 AS available_factor_count, 1.0 AS overall_coverage, 50.0 AS global_tipping_score, 'Cold' AS primary_driver
    UNION ALL SELECT 'cold_max', DATE '2026-01-03', 10.0, -10.0, 5.0, 20.0, 20.0, 20.0, TRUE, TRUE, 10.0, CAST(NULL AS FLOAT64), 50.0, 0.0, 10.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0, 1.0, 6, 5, 0.833, 50.0, 'Cold'
    UNION ALL SELECT 'tie_heat', DATE '2026-01-02', 20.0, -10.0, 5.0, 20.0, 20.0, 20.0, TRUE, TRUE, 10.0, 50.0, 50.0, 0.0, 10.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 6, 6, 1.0, 50.0, 'Heat'
    UNION ALL SELECT 'tie_heat', DATE '2026-01-03', 20.0, -10.0, 5.0, 20.0, 20.0, 20.0, TRUE, TRUE, 10.0, CAST(NULL AS FLOAT64), 50.0, 0.0, 10.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0, 1.0, 6, 5, 0.833, 50.0, 'Cold'
    UNION ALL SELECT 'tie_river', DATE '2026-01-02', 10.0, -10.0, 5.0, 20.0, 20.0, 100.0, TRUE, TRUE, 10.0, 0.0, 50.0, 0.0, 10.0, 0.0, 50.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 6, 6, 1.0, 50.0, 'River/Flood'
    UNION ALL SELECT 'tie_river', DATE '2026-01-03', 10.0, -10.0, 5.0, 20.0, 20.0, 125.0, TRUE, TRUE, 10.0, CAST(NULL AS FLOAT64), 50.0, 0.0, 10.0, 0.0, CAST(NULL AS FLOAT64), 0.0, 1.0, 1.0, 1.0, 1.0, 0.5, 6, 4, 0.75, 50.0, 'Cold'
    UNION ALL SELECT 'tie_wind', DATE '2026-01-02', 10.0, -10.0, 5.0, 60.0, 20.0, 20.0, TRUE, TRUE, 10.0, CAST(NULL AS FLOAT64), 50.0, 50.0, 10.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0, 1.0, 6, 5, 0.833, 50.0, 'Wind'
    UNION ALL SELECT 'tie_rain', DATE '2026-01-02', 10.0, -10.0, 25.0, 20.0, 20.0, 20.0, TRUE, TRUE, 10.0, CAST(NULL AS FLOAT64), 50.0, 0.0, 50.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0, 1.0, 6, 5, 0.833, 50.0, 'Rain'
    UNION ALL SELECT 'tie_air', DATE '2026-01-02', 10.0, -20.0, 5.0, 20.0, 100.0, 20.0, TRUE, TRUE, 20.0, CAST(NULL AS FLOAT64), 100.0, 0.0, 10.0, 100.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0, 1.0, 6, 5, 0.833, 100.0, 'Air Quality'
    UNION ALL SELECT 'zero_cold', DATE '2026-01-02', 10.0, 0.0, 0.0, 20.0, 20.0, 20.0, TRUE, TRUE, 0.0, CAST(NULL AS FLOAT64), 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0, 1.0, 6, 5, 0.833, 0.0, 'Stable'
    UNION ALL SELECT 'cold_only_available', DATE '2026-01-02', CAST(NULL AS FLOAT64), -10.0, CAST(NULL AS FLOAT64), CAST(NULL AS FLOAT64), CAST(NULL AS FLOAT64), CAST(NULL AS FLOAT64), TRUE, TRUE, 10.0, CAST(NULL AS FLOAT64), 50.0, CAST(NULL AS FLOAT64), CAST(NULL AS FLOAT64), CAST(NULL AS FLOAT64), CAST(NULL AS FLOAT64), 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 6, 1, 0.167, 50.0, 'Cold'
    UNION ALL SELECT 'all_unavailable', DATE '2026-01-02', CAST(NULL AS FLOAT64), CAST(NULL AS FLOAT64), CAST(NULL AS FLOAT64), CAST(NULL AS FLOAT64), CAST(NULL AS FLOAT64), CAST(NULL AS FLOAT64), TRUE, TRUE, CAST(NULL AS FLOAT64), CAST(NULL AS FLOAT64), CAST(NULL AS FLOAT64), CAST(NULL AS FLOAT64), CAST(NULL AS FLOAT64), CAST(NULL AS FLOAT64), CAST(NULL AS FLOAT64), 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 6, 0, 0.0, CAST(NULL AS FLOAT64), 'Unavailable'
    UNION ALL SELECT 'cold_not_monitored', DATE '2026-01-02', 10.0, -20.0, 5.0, 20.0, 20.0, 20.0, TRUE, FALSE, 20.0, CAST(NULL AS FLOAT64), CAST(NULL AS FLOAT64), 0.0, 10.0, 0.0, 0.0, 0.0, CAST(NULL AS FLOAT64), 1.0, 1.0, 1.0, 1.0, 5, 4, 0.8, 10.0, 'Rain'
    UNION ALL SELECT 'partial_cold', DATE '2026-01-02', 10.0, -10.0, 5.0, 20.0, 20.0, 20.0, TRUE, TRUE, CAST(NULL AS FLOAT64), CAST(NULL AS FLOAT64), CAST(NULL AS FLOAT64), 0.0, 10.0, 0.0, 0.0, 0.0, 0.958, 1.0, 1.0, 1.0, 1.0, 6, 4, 0.826, 10.0, 'Rain'
    UNION ALL SELECT 'raw_coverage_rounding', DATE '2026-01-02', 10.0, -10.0, 5.0, 20.0, 20.0, CAST(NULL AS FLOAT64), TRUE, TRUE, CAST(NULL AS FLOAT64), CAST(NULL AS FLOAT64), CAST(NULL AS FLOAT64), CAST(NULL AS FLOAT64), CAST(NULL AS FLOAT64), CAST(NULL AS FLOAT64), CAST(NULL AS FLOAT64), 0.0, 0.958, 0.042, 0.042, 0.125, 0.0, 6, 0, 0.194, CAST(NULL AS FLOAT64), 'Unavailable'
    UNION ALL SELECT 'all_not_monitored', DATE '2026-01-02', 10.0, -10.0, 5.0, 20.0, 20.0, 20.0, FALSE, FALSE, 10.0, CAST(NULL AS FLOAT64), CAST(NULL AS FLOAT64), CAST(NULL AS FLOAT64), CAST(NULL AS FLOAT64), CAST(NULL AS FLOAT64), CAST(NULL AS FLOAT64), CAST(NULL AS FLOAT64), CAST(NULL AS FLOAT64), CAST(NULL AS FLOAT64), CAST(NULL AS FLOAT64), CAST(NULL AS FLOAT64), CAST(NULL AS FLOAT64), 0, 0, CAST(NULL AS FLOAT64), CAST(NULL AS FLOAT64), 'Unavailable'
    UNION ALL SELECT 'all_tied', DATE '2026-01-02', 30.0, -20.0, 50.0, 80.0, 100.0, 100.0, TRUE, TRUE, 20.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 6, 6, 1.0, 100.0, 'Heat'
    UNION ALL SELECT 'all_tied', DATE '2026-01-03', 30.0, -20.0, 50.0, 80.0, 100.0, 150.0, TRUE, TRUE, 20.0, CAST(NULL AS FLOAT64), 100.0, 100.0, 100.0, 100.0, CAST(NULL AS FLOAT64), 0.0, 1.0, 1.0, 1.0, 1.0, 0.5, 6, 4, 0.75, 100.0, 'Wind'
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
    TRUE AS weather_source_available,
    TIMESTAMP '2026-01-01 06:00:00+00' AS weather_ingested_at_utc,
    TRUE AS air_quality_source_available,
    TIMESTAMP '2026-01-01 06:00:00+00' AS air_quality_ingested_at_utc,
    TRUE AS flood_source_available,
    TIMESTAMP '2026-01-01 06:00:00+00' AS flood_ingested_at_utc,
    temperature_2m_max,
    temperature_2m_min,
    0.0 AS normal_temperature_2m_min,
    cold_anomaly_c,
    precipitation_sum_mm,
    wind_gusts_10m_max,
    european_aqi_max,
    river_discharge_m3s,
    heat_score,
    cold_score,
    wind_score,
    rain_score,
    air_score,
    river_score,
    CASE WHEN NOT monitored THEN 'not_monitored'
        WHEN heat_score IS NULL THEN 'unavailable' ELSE 'available' END AS heat_status,
    monitored AS heat_monitored,
    heat_score IS NOT NULL AS heat_available,
    heat_coverage,
    CASE WHEN NOT cold_monitored THEN 'not_monitored'
        WHEN cold_score IS NULL THEN 'unavailable' ELSE 'available' END AS cold_status,
    cold_monitored AS cold_monitored,
    cold_score IS NOT NULL AS cold_available,
    cold_coverage,
    CASE WHEN NOT monitored THEN 'not_monitored'
        WHEN wind_score IS NULL THEN 'unavailable' ELSE 'available' END AS wind_status,
    monitored AS wind_monitored,
    wind_score IS NOT NULL AS wind_available,
    wind_coverage,
    CASE WHEN NOT monitored THEN 'not_monitored'
        WHEN rain_score IS NULL THEN 'unavailable' ELSE 'available' END AS rain_status,
    monitored AS rain_monitored,
    rain_score IS NOT NULL AS rain_available,
    rain_coverage,
    CASE WHEN NOT monitored THEN 'not_monitored'
        WHEN air_score IS NULL THEN 'unavailable' ELSE 'available' END AS air_status,
    monitored AS air_monitored,
    air_score IS NOT NULL AS air_available,
    air_coverage,
    CASE WHEN NOT monitored THEN 'not_monitored'
        WHEN river_score IS NULL THEN 'unavailable' ELSE 'available' END AS river_status,
    monitored AS river_monitored,
    river_score IS NOT NULL AS river_available,
    river_coverage,
    monitored_factor_count,
    available_factor_count,
    overall_coverage,
    global_tipping_score IS NOT NULL AS global_score_available,
    global_tipping_score,
    primary_driver,
    TRUE AS cold_in_global_score
FROM expected
