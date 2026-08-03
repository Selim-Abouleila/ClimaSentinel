-- The v2 contract must retain every configured monitoring city even when its
-- selected-run weather payload is completely absent. Today through Day +2 are
-- required upstream so both current dates and tomorrow's velocity inputs exist.

WITH operational_dates AS (
    SELECT operational_date AS date
    FROM UNNEST(
        GENERATE_DATE_ARRAY(
            CURRENT_DATE('UTC'),
            DATE_ADD(CURRENT_DATE('UTC'), INTERVAL 2 DAY)
        )
    ) AS operational_date
),

expected_city_dates AS (
    SELECT monitoring.city_id, operational_dates.date
    FROM {{ ref('city_signal_monitoring') }} AS monitoring
    CROSS JOIN operational_dates
),

history_counts AS (
    SELECT
        expected.city_id,
        expected.date,
        COUNT(history.city_id) AS row_count
    FROM expected_city_dates AS expected
    LEFT JOIN {{ ref('mart_city_score_history_v2') }} AS history
        ON expected.city_id = history.city_id
        AND expected.date = history.date
    GROUP BY expected.city_id, expected.date
),

history_violations AS (
    SELECT
        'missing_or_duplicate_history_spine_row' AS violation,
        city_id,
        date
    FROM history_counts
    WHERE row_count != 1
),

current_counts AS (
    SELECT
        monitoring.city_id,
        COUNT(current_scores.city_id) AS row_count
    FROM {{ ref('city_signal_monitoring') }} AS monitoring
    LEFT JOIN {{ ref('mart_city_score_current_v2') }} AS current_scores
        ON monitoring.city_id = current_scores.city_id
    GROUP BY monitoring.city_id
),

current_violations AS (
    SELECT
        'missing_or_duplicate_current_city' AS violation,
        city_id,
        CAST(NULL AS DATE) AS date
    FROM current_counts
    WHERE row_count != 1
),

detail_counts AS (
    SELECT
        monitoring.city_id,
        COUNT(detail.city_id) AS row_count
    FROM {{ ref('city_signal_monitoring') }} AS monitoring
    LEFT JOIN {{ ref('mart_city_score_detail_v2') }} AS detail
        ON monitoring.city_id = detail.city_id
    GROUP BY monitoring.city_id
),

detail_violations AS (
    SELECT
        'missing_or_duplicate_detail_city' AS violation,
        city_id,
        CAST(NULL AS DATE) AS date
    FROM detail_counts
    WHERE row_count != 1
),

zone_violations AS (
    SELECT
        'zone_city_total_mismatch' AS violation,
        CAST(NULL AS STRING) AS city_id,
        CAST(NULL AS DATE) AS date
    FROM {{ ref('mart_city_zone_current_v2') }}
    HAVING COALESCE(SUM(city_count), 0) != (
        SELECT COUNT(*) FROM {{ ref('city_signal_monitoring') }}
    )
)

SELECT * FROM history_violations
UNION ALL
SELECT * FROM current_violations
UNION ALL
SELECT * FROM detail_violations
UNION ALL
SELECT * FROM zone_violations
