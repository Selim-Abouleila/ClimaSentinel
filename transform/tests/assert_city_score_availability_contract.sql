-- A score of zero is a valid measurement. NULL is the only representation of
-- an unavailable/not-monitored factor, and all metadata must agree with it.

WITH factor_rows AS (
    SELECT
        city_id,
        date,
        factor.factor_name,
        factor.score,
        factor.status,
        factor.monitored,
        factor.available,
        factor.coverage
    FROM {{ ref('mart_city_score_history_v2') }}
    CROSS JOIN UNNEST([
        STRUCT(
            'heat' AS factor_name,
            heat_score AS score,
            heat_status AS status,
            heat_monitored AS monitored,
            heat_available AS available,
            heat_coverage AS coverage
        ),
        STRUCT(
            'wind' AS factor_name,
            wind_score AS score,
            wind_status AS status,
            wind_monitored AS monitored,
            wind_available AS available,
            wind_coverage AS coverage
        ),
        STRUCT(
            'rain' AS factor_name,
            rain_score AS score,
            rain_status AS status,
            rain_monitored AS monitored,
            rain_available AS available,
            rain_coverage AS coverage
        ),
        STRUCT(
            'air' AS factor_name,
            air_score AS score,
            air_status AS status,
            air_monitored AS monitored,
            air_available AS available,
            air_coverage AS coverage
        ),
        STRUCT(
            'river' AS factor_name,
            river_score AS score,
            river_status AS status,
            river_monitored AS monitored,
            river_available AS available,
            river_coverage AS coverage
        )
    ]) AS factor
),

factor_violations AS (
    SELECT
        'factor_metadata_mismatch' AS violation,
        city_id,
        date,
        factor_name
    FROM factor_rows
    WHERE status IS NULL
        OR monitored IS NULL
        OR available IS NULL
        OR status NOT IN ('available', 'not_monitored', 'unavailable')
        OR coverage < 0
        OR coverage > 1
        OR (
            status = 'available'
            AND (
                NOT monitored
                OR NOT available
                OR score IS NULL
                OR coverage IS DISTINCT FROM 1.0
            )
        )
        OR (
            status = 'not_monitored'
            AND (monitored OR available OR score IS NOT NULL OR coverage IS NOT NULL)
        )
        OR (
            status = 'unavailable'
            AND (
                NOT monitored
                OR available
                OR score IS NOT NULL
                OR coverage IS NULL
                OR coverage >= 1.0
            )
        )
),

global_expectations AS (
    SELECT
        *,
        (
            SELECT MAX(score)
            FROM UNNEST([
                heat_score,
                wind_score,
                rain_score,
                air_score,
                river_score
            ]) AS score
        ) AS expected_global_score,
        (
            IF(heat_monitored, 1, 0)
            + IF(wind_monitored, 1, 0)
            + IF(rain_monitored, 1, 0)
            + IF(air_monitored, 1, 0)
            + IF(river_monitored, 1, 0)
        ) AS expected_monitored_count,
        (
            IF(heat_available, 1, 0)
            + IF(wind_available, 1, 0)
            + IF(rain_available, 1, 0)
            + IF(air_available, 1, 0)
            + IF(river_available, 1, 0)
        ) AS expected_available_count,
        ROUND(
            SAFE_DIVIDE(
                COALESCE(heat_coverage, 0.0)
                + COALESCE(wind_coverage, 0.0)
                + COALESCE(rain_coverage, 0.0)
                + COALESCE(air_coverage, 0.0)
                + COALESCE(river_coverage, 0.0),
                IF(heat_monitored, 1, 0)
                + IF(wind_monitored, 1, 0)
                + IF(rain_monitored, 1, 0)
                + IF(air_monitored, 1, 0)
                + IF(river_monitored, 1, 0)
            ),
            3
        ) AS expected_overall_coverage
    FROM {{ ref('mart_city_score_history_v2') }}
),

global_violations AS (
    SELECT
        'global_score_mismatch' AS violation,
        city_id,
        date,
        CAST(NULL AS STRING) AS factor_name
    FROM global_expectations
    WHERE global_tipping_score IS DISTINCT FROM expected_global_score
        OR global_score_available IS DISTINCT FROM (expected_global_score IS NOT NULL)
        OR monitored_factor_count IS DISTINCT FROM expected_monitored_count
        OR available_factor_count IS DISTINCT FROM expected_available_count
        OR overall_coverage IS DISTINCT FROM expected_overall_coverage
        OR (
            expected_global_score IS NULL
            AND primary_driver IS DISTINCT FROM 'Unavailable'
        )
        OR (
            river_monitored
            AND river_discharge_m3s IS NOT NULL
            AND river_discharge_m3s <= 50
            AND river_score IS DISTINCT FROM 0.0
        )
)

SELECT * FROM factor_violations
UNION ALL
SELECT * FROM global_violations
