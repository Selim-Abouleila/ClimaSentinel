{{ config(
    materialized='view'
) }}

WITH scored_cities AS (
    SELECT
        city_id,
        current_tipping_score,
        current_primary_driver,
        CASE
            WHEN current_tipping_score >= 81 THEN '🔴 Critical'
            WHEN current_tipping_score >= 61 THEN '🟠 Tipping'
            WHEN current_tipping_score >= 31 THEN '🟡 Monitoring'
            ELSE '🟢 Stable'
        END AS zone_name,
        CASE
            WHEN current_tipping_score >= 81 THEN 1
            WHEN current_tipping_score >= 61 THEN 2
            WHEN current_tipping_score >= 31 THEN 3
            ELSE 4
        END AS zone_order
    FROM {{ ref('mart_city_score_current') }}
)

SELECT
    zone_name,
    COUNT(city_id) AS city_count,
    STRING_AGG(city_id, ', ') AS cities_in_zone,
    -- List the primary drivers causing tension in this zone
    STRING_AGG(DISTINCT current_primary_driver, ', ') AS drivers_in_zone
FROM scored_cities
GROUP BY zone_name, zone_order
ORDER BY zone_order ASC
