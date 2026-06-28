{{ config(
    materialized='table',
    partition_by={
      "field": "date",
      "data_type": "date",
      "granularity": "day"
    }
) }}

WITH feature_base AS (
    SELECT 
        f.city_id,
        f.date,
        s.global_tipping_score AS current_tipping_score,
        
        -- Current weather signals (t0)
        f.temperature_2m_max,
        f.temperature_2m_min,
        f.precipitation_sum_mm,
        f.wind_speed_10m_max,
        f.european_aqi_max,
        f.river_discharge_m3s,
        
        -- Future weather forecast features (t+1, t+2, t+3)
        LEAD(f.temperature_2m_max, 1) OVER (PARTITION BY f.city_id ORDER BY f.date) AS temp_forecast_plus_1d,
        LEAD(f.temperature_2m_max, 2) OVER (PARTITION BY f.city_id ORDER BY f.date) AS temp_forecast_plus_2d,
        LEAD(f.temperature_2m_max, 3) OVER (PARTITION BY f.city_id ORDER BY f.date) AS temp_forecast_plus_3d,
        
        LEAD(f.precipitation_sum_mm, 1) OVER (PARTITION BY f.city_id ORDER BY f.date) AS precip_forecast_plus_1d,
        LEAD(f.precipitation_sum_mm, 2) OVER (PARTITION BY f.city_id ORDER BY f.date) AS precip_forecast_plus_2d,
        LEAD(f.precipitation_sum_mm, 3) OVER (PARTITION BY f.city_id ORDER BY f.date) AS precip_forecast_plus_3d,
        
        LEAD(f.wind_speed_10m_max, 1) OVER (PARTITION BY f.city_id ORDER BY f.date) AS wind_forecast_plus_1d,
        LEAD(f.wind_speed_10m_max, 2) OVER (PARTITION BY f.city_id ORDER BY f.date) AS wind_forecast_plus_2d,
        LEAD(f.wind_speed_10m_max, 3) OVER (PARTITION BY f.city_id ORDER BY f.date) AS wind_forecast_plus_3d,
        
        -- Target Variable (t+3)
        LEAD(s.global_tipping_score, 3) OVER (PARTITION BY f.city_id ORDER BY f.date) AS future_tipping_score_3d

    FROM {{ ref('stg_city_signal_input') }} f
    LEFT JOIN {{ ref('mart_city_score_history') }} s
        ON f.city_id = s.city_id AND f.date = s.date
)

SELECT * FROM feature_base
