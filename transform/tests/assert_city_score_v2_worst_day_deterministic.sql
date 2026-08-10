-- The selected detail row must be the exact complete history row dictated by
-- the v2 ordering contract. This protects measured ties from regressing to
-- independent ANY_VALUE aggregates that can mix dates or factor metadata.

WITH expected AS (
    SELECT *
    FROM {{ ref('mart_city_score_history_v2') }}
    WHERE date BETWEEN CURRENT_DATE('UTC')
        AND DATE_ADD(CURRENT_DATE('UTC'), INTERVAL 1 DAY)
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY city_id
        ORDER BY global_score_available DESC, global_tipping_score DESC, date ASC
    ) = 1
),

actual AS (
    SELECT *
    FROM {{ ref('mart_city_score_detail_v2') }}
)

SELECT
    expected.city_id,
    expected.date AS expected_score_date,
    actual.score_date AS actual_score_date
FROM expected
LEFT JOIN actual
    ON expected.city_id = actual.city_id
WHERE actual.city_id IS NULL
    OR actual.score_date IS DISTINCT FROM expected.date
    OR actual.current_tipping_score IS DISTINCT FROM expected.global_tipping_score
    OR actual.current_primary_driver IS DISTINCT FROM expected.primary_driver
    OR actual.heat_score IS DISTINCT FROM expected.heat_score
    OR actual.wind_score IS DISTINCT FROM expected.wind_score
    OR actual.rain_score IS DISTINCT FROM expected.rain_score
    OR actual.air_score IS DISTINCT FROM expected.air_score
    OR actual.river_score IS DISTINCT FROM expected.river_score
    OR actual.heat_status IS DISTINCT FROM expected.heat_status
    OR actual.wind_status IS DISTINCT FROM expected.wind_status
    OR actual.rain_status IS DISTINCT FROM expected.rain_status
    OR actual.air_status IS DISTINCT FROM expected.air_status
    OR actual.river_status IS DISTINCT FROM expected.river_status
