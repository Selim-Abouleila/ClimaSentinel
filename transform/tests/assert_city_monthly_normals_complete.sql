-- Each city represented by the normals seed must have exactly one row for each
-- calendar month. Cross-file validation of active config cities happens in
-- scripts/validate_city_configuration.py before dbt runs.

WITH cities AS (
    SELECT DISTINCT city_id
    FROM {{ ref('city_monthly_normals') }}
),

expected AS (
    SELECT
        city_id,
        month
    FROM cities
    CROSS JOIN UNNEST(GENERATE_ARRAY(1, 12)) AS month
),

observed AS (
    SELECT
        city_id,
        month,
        COUNT(*) AS row_count
    FROM {{ ref('city_monthly_normals') }}
    GROUP BY city_id, month
)

SELECT
    expected.city_id,
    expected.month,
    COALESCE(observed.row_count, 0) AS observed_rows
FROM expected
LEFT JOIN observed
    USING (city_id, month)
WHERE COALESCE(observed.row_count, 0) != 1

UNION ALL

SELECT
    city_id,
    month,
    row_count AS observed_rows
FROM observed
WHERE month NOT BETWEEN 1 AND 12
