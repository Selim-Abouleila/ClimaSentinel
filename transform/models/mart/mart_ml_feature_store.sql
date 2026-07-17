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
        
        -- Historical Baseline
        n.normal_temperature_2m_max,
        
        -- Current weather signals (t0)
        f.temperature_2m_max,
        f.temperature_2m_min,
        f.precipitation_sum_mm,
        f.wind_speed_10m_max,
        f.wind_gusts_10m_max,
        f.european_aqi_max,
        f.river_discharge_m3s,
        
        -- Future weather forecast features (t+1, t+2, t+3)
        LEAD(f.temperature_2m_max, 1) OVER (PARTITION BY f.city_id ORDER BY f.date) AS temp_forecast_plus_1d,
        LEAD(f.temperature_2m_max, 2) OVER (PARTITION BY f.city_id ORDER BY f.date) AS temp_forecast_plus_2d,
        LEAD(f.temperature_2m_max, 3) OVER (PARTITION BY f.city_id ORDER BY f.date) AS temp_forecast_plus_3d,
        LEAD(f.temperature_2m_max, 4) OVER (PARTITION BY f.city_id ORDER BY f.date) AS temp_forecast_plus_4d,
        
        LEAD(f.precipitation_sum_mm, 1) OVER (PARTITION BY f.city_id ORDER BY f.date) AS precip_forecast_plus_1d,
        LEAD(f.precipitation_sum_mm, 2) OVER (PARTITION BY f.city_id ORDER BY f.date) AS precip_forecast_plus_2d,
        LEAD(f.precipitation_sum_mm, 3) OVER (PARTITION BY f.city_id ORDER BY f.date) AS precip_forecast_plus_3d,
        
        LEAD(f.wind_speed_10m_max, 1) OVER (PARTITION BY f.city_id ORDER BY f.date) AS wind_forecast_plus_1d,
        LEAD(f.wind_speed_10m_max, 2) OVER (PARTITION BY f.city_id ORDER BY f.date) AS wind_forecast_plus_2d,
        LEAD(f.wind_speed_10m_max, 3) OVER (PARTITION BY f.city_id ORDER BY f.date) AS wind_forecast_plus_3d,

        LEAD(f.wind_gusts_10m_max, 1) OVER (PARTITION BY f.city_id ORDER BY f.date) AS wind_gusts_forecast_plus_1d,
        LEAD(f.wind_gusts_10m_max, 2) OVER (PARTITION BY f.city_id ORDER BY f.date) AS wind_gusts_forecast_plus_2d,
        LEAD(f.wind_gusts_10m_max, 3) OVER (PARTITION BY f.city_id ORDER BY f.date) AS wind_gusts_forecast_plus_3d,

        LEAD(f.european_aqi_max, 1) OVER (PARTITION BY f.city_id ORDER BY f.date) AS aqi_forecast_plus_1d,
        LEAD(f.european_aqi_max, 2) OVER (PARTITION BY f.city_id ORDER BY f.date) AS aqi_forecast_plus_2d,
        LEAD(f.european_aqi_max, 3) OVER (PARTITION BY f.city_id ORDER BY f.date) AS aqi_forecast_plus_3d,

        LEAD(f.river_discharge_m3s, 1) OVER (PARTITION BY f.city_id ORDER BY f.date) AS river_forecast_plus_1d,
        LEAD(f.river_discharge_m3s, 2) OVER (PARTITION BY f.city_id ORDER BY f.date) AS river_forecast_plus_2d,
        LEAD(f.river_discharge_m3s, 3) OVER (PARTITION BY f.city_id ORDER BY f.date) AS river_forecast_plus_3d,
        LEAD(f.river_discharge_m3s, 4) OVER (PARTITION BY f.city_id ORDER BY f.date) AS river_forecast_plus_4d,
        
        -- Target Variables (t+1) - Multi-Output Regression
        LEAD(s.heat_score, 1) OVER (PARTITION BY f.city_id ORDER BY f.date) AS future_heat_score_1d,
        LEAD(s.wind_score, 1) OVER (PARTITION BY f.city_id ORDER BY f.date) AS future_wind_score_1d,
        LEAD(s.rain_score, 1) OVER (PARTITION BY f.city_id ORDER BY f.date) AS future_rain_score_1d,
        LEAD(s.air_score, 1) OVER (PARTITION BY f.city_id ORDER BY f.date) AS future_air_score_1d,
        LEAD(s.river_score, 1) OVER (PARTITION BY f.city_id ORDER BY f.date) AS future_river_score_1d,
        LEAD(s.global_tipping_score, 1) OVER (PARTITION BY f.city_id ORDER BY f.date) AS future_tipping_score_1d,

        -- Target Variables (t+2) - Multi-Output Regression
        LEAD(s.heat_score, 2) OVER (PARTITION BY f.city_id ORDER BY f.date) AS future_heat_score_2d,
        LEAD(s.wind_score, 2) OVER (PARTITION BY f.city_id ORDER BY f.date) AS future_wind_score_2d,
        LEAD(s.rain_score, 2) OVER (PARTITION BY f.city_id ORDER BY f.date) AS future_rain_score_2d,
        LEAD(s.air_score, 2) OVER (PARTITION BY f.city_id ORDER BY f.date) AS future_air_score_2d,
        LEAD(s.river_score, 2) OVER (PARTITION BY f.city_id ORDER BY f.date) AS future_river_score_2d,
        LEAD(s.global_tipping_score, 2) OVER (PARTITION BY f.city_id ORDER BY f.date) AS future_tipping_score_2d,

        -- Target Variables (t+3) - Multi-Output Regression
        LEAD(s.heat_score, 3) OVER (PARTITION BY f.city_id ORDER BY f.date) AS future_heat_score_3d,
        LEAD(s.wind_score, 3) OVER (PARTITION BY f.city_id ORDER BY f.date) AS future_wind_score_3d,
        LEAD(s.rain_score, 3) OVER (PARTITION BY f.city_id ORDER BY f.date) AS future_rain_score_3d,
        LEAD(s.air_score, 3) OVER (PARTITION BY f.city_id ORDER BY f.date) AS future_air_score_3d,
        LEAD(s.river_score, 3) OVER (PARTITION BY f.city_id ORDER BY f.date) AS future_river_score_3d,
        LEAD(s.global_tipping_score, 3) OVER (PARTITION BY f.city_id ORDER BY f.date) AS future_tipping_score_3d

    FROM {{ ref('stg_city_signal_input') }} f
    LEFT JOIN {{ ref('mart_city_score_history') }} s
        ON f.city_id = s.city_id AND f.date = s.date
    LEFT JOIN {{ ref('city_monthly_normals') }} n
        ON f.city_id = n.city_id AND EXTRACT(MONTH FROM f.date) = n.month
)

SELECT * FROM feature_base
