-- Verify source/baseline lineage and availability independently of score logic.
WITH diagnostics AS (
    SELECT
        history.city_id,
        history.date,
        history.temperature_2m_min,
        history.normal_temperature_2m_min,
        history.cold_anomaly_c,
        signals.city_id AS source_city_id,
        signals.temperature_2m_min AS source_minimum,
        normals.normal_temperature_2m_min AS source_normal,
        COALESCE(
            signals.temperature_2m_value_count = 24
            AND signals.temperature_2m_min IS NOT NULL
            AND NOT IS_NAN(signals.temperature_2m_min)
            AND NOT IS_INF(signals.temperature_2m_min)
            AND normals.normal_temperature_2m_min IS NOT NULL
            AND NOT IS_NAN(normals.normal_temperature_2m_min)
            AND NOT IS_INF(normals.normal_temperature_2m_min),
            FALSE
        ) AS anomaly_expected
    FROM {{ ref('mart_city_score_history_v2') }} AS history
    LEFT JOIN {{ ref('stg_city_signal_input_v2') }} AS signals
        ON history.operational_ingestion_run_id = signals.operational_ingestion_run_id
        AND history.city_id = signals.city_id
        AND history.date = signals.date
    LEFT JOIN {{ ref('city_monthly_normals') }} AS normals
        ON history.city_id = normals.city_id
        AND EXTRACT(MONTH FROM history.date) = normals.month
)

SELECT city_id, date, cold_anomaly_c
FROM diagnostics
WHERE source_city_id IS NULL
    OR temperature_2m_min IS DISTINCT FROM source_minimum
    OR normal_temperature_2m_min IS DISTINCT FROM source_normal
    OR (cold_anomaly_c IS NOT NULL) IS DISTINCT FROM anomaly_expected
    OR IS_NAN(cold_anomaly_c)
    OR IS_INF(cold_anomaly_c)
    OR cold_anomaly_c < 0
