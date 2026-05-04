{{ config(
    materialized='view'
) }}

WITH current_window AS (
    SELECT
        city_id,
        global_tipping_score,
        primary_driver
    FROM {{ ref('mart_city_score_history') }}
    -- Look at the 48-hour operational window (today and tomorrow)
    WHERE date BETWEEN CURRENT_DATE('UTC') AND DATE_ADD(CURRENT_DATE('UTC'), INTERVAL 1 DAY)
),

aggregated AS (
    SELECT
        city_id,
        -- Take the maximum score over the next 48 hours to represent current tension
        MAX(global_tipping_score) AS current_tipping_score,
        
        -- We string_agg the primary drivers in case they change between today and tomorrow,
        -- but realistically we just want the driver that caused the max score. 
        -- To keep it simple, we grab the driver associated with the highest score.
        ANY_VALUE(primary_driver HAVING MAX global_tipping_score) AS current_primary_driver
    FROM current_window
    GROUP BY city_id
)

SELECT
    city_id,
    current_tipping_score,
    current_primary_driver,
    -- Rank cities from 1 (Most Tense) to N (Least Tense)
    RANK() OVER (ORDER BY current_tipping_score DESC) AS rank
FROM aggregated
ORDER BY rank ASC
