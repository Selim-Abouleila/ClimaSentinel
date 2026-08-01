{{ config(tags=['forecast_vintage']) }}

-- The forecast scope is intentionally frozen at the original ten cities.
-- Expanding this contract requires an explicit seed and test change.

WITH expected AS (
    SELECT *
    FROM UNNEST([
        STRUCT('paris_fr' AS city_id, 'Europe/Paris' AS time_zone),
        STRUCT('london_gb' AS city_id, 'Europe/London' AS time_zone),
        STRUCT('madrid_es' AS city_id, 'Europe/Madrid' AS time_zone),
        STRUCT('berlin_de' AS city_id, 'Europe/Berlin' AS time_zone),
        STRUCT('rome_it' AS city_id, 'Europe/Rome' AS time_zone),
        STRUCT('amsterdam_nl' AS city_id, 'Europe/Amsterdam' AS time_zone),
        STRUCT('athens_gr' AS city_id, 'Europe/Athens' AS time_zone),
        STRUCT('warsaw_pl' AS city_id, 'Europe/Warsaw' AS time_zone),
        STRUCT('lisbon_pt' AS city_id, 'Europe/Lisbon' AS time_zone),
        STRUCT('stockholm_se' AS city_id, 'Europe/Stockholm' AS time_zone)
    ])
),

actual AS (
    SELECT
        city_id,
        forecast_origin_time_zone AS time_zone
    FROM {{ ref('forecast_city_allowlist') }}
)

SELECT 'missing_or_changed' AS violation, city_id, time_zone
FROM (
    SELECT * FROM expected
    EXCEPT DISTINCT
    SELECT * FROM actual
)

UNION ALL

SELECT 'unexpected' AS violation, city_id, time_zone
FROM (
    SELECT * FROM actual
    EXCEPT DISTINCT
    SELECT * FROM expected
)
