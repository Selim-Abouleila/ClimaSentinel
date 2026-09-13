-- Both consumers must select the same history row in either aggregate mode.
-- Rank follows the complete current city set, with unavailable cities last.
WITH expected AS (
    SELECT
        *,
        RANK() OVER (
            ORDER BY current_score_available DESC, current_tipping_score DESC
        ) AS expected_rank
    FROM {{ ref('mart_city_score_detail_v2') }}
)

SELECT
    COALESCE(current_scores.city_id, expected.city_id) AS city_id
FROM {{ ref('mart_city_score_current_v2') }} AS current_scores
FULL OUTER JOIN expected
    ON current_scores.city_id = expected.city_id
WHERE current_scores.city_id IS NULL
    OR expected.city_id IS NULL
    OR current_scores.operational_ingestion_run_id IS DISTINCT FROM expected.operational_ingestion_run_id
    OR current_scores.operational_ingested_at_utc IS DISTINCT FROM expected.operational_ingested_at_utc
    OR current_scores.current_tipping_score IS DISTINCT FROM expected.current_tipping_score
    OR current_scores.current_primary_driver IS DISTINCT FROM expected.current_primary_driver
    OR current_scores.current_score_available IS DISTINCT FROM expected.current_score_available
    OR current_scores.monitored_factor_count IS DISTINCT FROM expected.monitored_factor_count
    OR current_scores.available_factor_count IS DISTINCT FROM expected.available_factor_count
    OR current_scores.overall_coverage IS DISTINCT FROM expected.overall_coverage
    OR current_scores.rank IS DISTINCT FROM expected.expected_rank
