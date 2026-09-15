-- Reject invalid temperature baselines in BigQuery as well as in the CSV
-- validator. Zero and negative minimum-temperature normals are valid.
SELECT
    city_id,
    month,
    normal_temperature_2m_min,
    normal_temperature_2m_mean,
    normal_temperature_2m_max
FROM {{ ref('city_monthly_normals') }}
WHERE
    normal_temperature_2m_min IS NULL
    OR IS_NAN(normal_temperature_2m_min)
    OR IS_INF(normal_temperature_2m_min)
    OR normal_temperature_2m_min NOT BETWEEN -90 AND 60
    OR normal_temperature_2m_min > normal_temperature_2m_mean
    OR normal_temperature_2m_mean > normal_temperature_2m_max
