{{ config(
    materialized='table',
    partition_by={
      "field": "date",
      "data_type": "date",
      "granularity": "day"
    }
) }}

WITH daily_signals AS (
    SELECT
        s.*,
        EXTRACT(MONTH FROM s.date) AS month
    FROM {{ ref('stg_city_signal_input') }} s
),

signals_with_baselines AS (
    SELECT
        s.*,
        n.normal_temperature_2m_max
    FROM daily_signals s
    LEFT JOIN {{ ref('city_monthly_normals') }} n
        ON s.city_id = n.city_id AND s.month = n.month
),

signals_with_velocity AS (
    SELECT
        *,
        -- Temperature velocity: Temp tomorrow - Temp today
        COALESCE(
            LEAD(temperature_2m_max) OVER(PARTITION BY city_id ORDER BY date) - temperature_2m_max, 
            0
        ) AS temp_velocity,
        
        -- River velocity: (River tomorrow - River today) / River today
        CASE 
            WHEN river_discharge_m3s IS NOT NULL AND river_discharge_m3s > 0 THEN
                COALESCE(
                    (LEAD(river_discharge_m3s) OVER(PARTITION BY city_id ORDER BY date) - river_discharge_m3s) / river_discharge_m3s,
                    0
                )
            ELSE 0
        END AS river_velocity_pct
    FROM signals_with_baselines
),

factor_scores AS (
    SELECT
        *,
        -- 🌡️ Heat Score: (Anomaly * 5) + (Positive Velocity * 5)
        GREATEST(0, LEAST(100, 
            ((temperature_2m_max - normal_temperature_2m_max) * 5) + 
            (GREATEST(0, temp_velocity) * 5)
        )) AS heat_score,

        -- 💨 Wind Score: Gusts over 40 km/h * 2.5
        GREATEST(0, LEAST(100, 
            GREATEST(0, wind_gusts_10m_max - 40) * 2.5
        )) AS wind_score,

        -- 🌧️ Rain Score: Daily rain * 2
        GREATEST(0, LEAST(100, 
            precipitation_sum_mm * 2
        )) AS rain_score,

        -- 🌫️ Air Quality Score: Direct mapping of AQI
        GREATEST(0, LEAST(100, 
            COALESCE(european_aqi_max, 0)
        )) AS air_score,

        -- 🌊 River Score: Positive velocity percentage * 200
        GREATEST(0, LEAST(100, 
            GREATEST(0, river_velocity_pct) * 200
        )) AS river_score

    FROM signals_with_velocity
),

final_scores AS (
    SELECT
        city_id,
        date,
        -- Raw values for context
        temperature_2m_max,
        precipitation_sum_mm,
        wind_gusts_10m_max,
        european_aqi_max,
        river_discharge_m3s,
        
        -- Sub-scores
        ROUND(heat_score, 1) AS heat_score,
        ROUND(wind_score, 1) AS wind_score,
        ROUND(rain_score, 1) AS rain_score,
        ROUND(air_score, 1) AS air_score,
        ROUND(river_score, 1) AS river_score,
        
        -- Global Tipping Score (MAX of all factors)
        ROUND(GREATEST(heat_score, wind_score, rain_score, air_score, river_score), 1) AS global_tipping_score
        
    FROM factor_scores
)

SELECT
    *,
    -- Determine the primary driver
    CASE
        WHEN global_tipping_score = 0 THEN 'Stable'
        WHEN global_tipping_score = heat_score THEN 'Heat'
        WHEN global_tipping_score = river_score THEN 'River/Flood'
        WHEN global_tipping_score = wind_score THEN 'Wind'
        WHEN global_tipping_score = rain_score THEN 'Rain'
        WHEN global_tipping_score = air_score THEN 'Air Quality'
        ELSE 'Unknown'
    END AS primary_driver
FROM final_scores
