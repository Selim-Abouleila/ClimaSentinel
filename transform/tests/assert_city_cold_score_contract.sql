-- Check Cold eligibility, monitoring lineage and partial-day coverage against
-- the selected source run. Literal scoring examples live in the unit fixture.
WITH inputs AS (
    SELECT
        history.city_id,
        history.date,
        history.cold_score,
        history.cold_status,
        history.cold_monitored,
        history.cold_available,
        history.cold_coverage,
        signals.city_id AS source_city_id,
        signals.cold_monitored AS source_monitored,
        signals.temperature_2m_value_count AS reading_count,
        COALESCE(
            history.temperature_2m_min IS NOT NULL
            AND NOT IS_NAN(history.temperature_2m_min)
            AND NOT IS_INF(history.temperature_2m_min)
            AND history.normal_temperature_2m_min IS NOT NULL
            AND NOT IS_NAN(history.normal_temperature_2m_min)
            AND NOT IS_INF(history.normal_temperature_2m_min),
            FALSE
        ) AS finite_inputs,
        COALESCE(
            history.cold_anomaly_c IS NOT NULL
            AND NOT IS_NAN(history.cold_anomaly_c)
            AND NOT IS_INF(history.cold_anomaly_c)
            AND history.cold_anomaly_c >= 0,
            FALSE
        ) AS valid_anomaly
    FROM {{ ref('mart_city_score_history_v2') }} AS history
    LEFT JOIN {{ ref('stg_city_signal_input_v2') }} AS signals
        ON history.operational_ingestion_run_id = signals.operational_ingestion_run_id
        AND history.city_id = signals.city_id
        AND history.date = signals.date
),

eligibility AS (
    SELECT
        *,
        COALESCE(
            cold_monitored
            AND finite_inputs
            AND reading_count = 24
            AND valid_anomaly,
            FALSE
        ) AS expected_available
    FROM inputs
),

expectations AS (
    SELECT
        *,
        CASE
            WHEN cold_monitored IS FALSE THEN 'not_monitored'
            WHEN expected_available THEN 'available'
            ELSE 'unavailable'
        END AS expected_status,
        CASE
            WHEN cold_monitored IS FALSE THEN CAST(NULL AS FLOAT64)
            WHEN expected_available THEN 1.0
            WHEN cold_monitored IS TRUE
                AND finite_inputs
                AND reading_count BETWEEN 1 AND 23
                THEN ROUND(reading_count / 24.0, 3)
            ELSE 0.0
        END AS expected_coverage
    FROM eligibility
)

SELECT city_id, date, cold_score, cold_status, cold_coverage
FROM expectations
WHERE source_city_id IS NULL
    OR source_monitored IS NULL
    OR cold_monitored IS DISTINCT FROM source_monitored
    OR cold_available IS DISTINCT FROM expected_available
    OR cold_status IS DISTINCT FROM expected_status
    OR cold_coverage IS DISTINCT FROM expected_coverage
    OR (cold_score IS NOT NULL) IS DISTINCT FROM expected_available
    OR IS_NAN(cold_score)
    OR IS_INF(cold_score)
    OR cold_score < 0
    OR cold_score > 100
    OR (finite_inputs AND reading_count = 24 AND NOT valid_anomaly)
