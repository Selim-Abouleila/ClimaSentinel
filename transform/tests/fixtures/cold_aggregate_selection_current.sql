-- Literal selected cities and ranks; all 15 CURRENT output columns are checked.
-- The two Cold-driven 90s share rank 1; rank 2 is skipped. The available zero
-- ranks before the unavailable city, and the outside-only city is absent.
WITH expected AS (
    SELECT 'cold_today' AS city_id,
        90.0 AS current_tipping_score,
        'Cold' AS current_primary_driver,
        TRUE AS current_score_available,
        6 AS monitored_factor_count,
        6 AS available_factor_count,
        1.0 AS overall_coverage,
        1 AS rank
    UNION ALL SELECT 'cold_tomorrow', 90.0, 'Cold', TRUE, 6, 6, 1.0, 1
    UNION ALL SELECT 'earlier_tie', 80.0, 'Rain', TRUE, 6, 6, 1.0, 3
    UNION ALL SELECT 'heat_tie', 70.0, 'Heat', TRUE, 6, 6, 1.0, 4
    UNION ALL SELECT 'unmonitored_cold', 60.0, 'River/Flood', TRUE, 5, 5, 1.0, 5
    UNION ALL SELECT 'partial_cold', 50.0, 'Rain', TRUE, 6, 4, 0.826, 6
    UNION ALL SELECT 'missing_cold', 40.0, 'Wind', TRUE, 6, 4, 0.667, 7
    UNION ALL SELECT 'air_tie', 35.0, 'Air Quality', TRUE, 6, 6, 1.0, 8
    UNION ALL SELECT 'outside_window', 30.0, 'Cold', TRUE, 6, 6, 1.0, 9
    UNION ALL SELECT 'zero_beats_unavailable', 0.0, 'Stable', TRUE, 6, 1, 0.167, 10
    UNION ALL SELECT 'both_unavailable', CAST(NULL AS FLOAT64), 'Unavailable', FALSE, 6, 0, 0.0, 11
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
    current_tipping_score,
    current_primary_driver,
    current_score_available,
    monitored_factor_count,
    available_factor_count,
    overall_coverage,
    rank
FROM expected
