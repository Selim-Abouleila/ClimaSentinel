-- Every operational city must have one explicit monitoring contract. The
-- repository validator separately checks this seed against config/cities.csv;
-- this warehouse test protects the seeded BigQuery contract and the Cold
-- monitoring flag passed through to the operational staging model.

WITH operational_cities AS (
    SELECT DISTINCT city_id
    FROM {{ ref('city_monthly_normals') }}
),

monitoring_cities AS (
    SELECT city_id
    FROM {{ ref('city_signal_monitoring') }}
),

membership_violations AS (
    SELECT 'missing_monitoring_city' AS violation, city_id
    FROM operational_cities
    WHERE city_id NOT IN (SELECT city_id FROM monitoring_cities)

    UNION ALL

    SELECT 'unknown_monitoring_city' AS violation, city_id
    FROM monitoring_cities
    WHERE city_id NOT IN (SELECT city_id FROM operational_cities)
),

configuration_violations AS (
    SELECT
        'required_factor_not_monitored' AS violation,
        city_id
    FROM {{ ref('city_signal_monitoring') }}
    WHERE NOT heat_monitored
        OR cold_monitored IS DISTINCT FROM TRUE
        OR NOT wind_monitored
        OR NOT rain_monitored
        OR NOT air_monitored
),

staging_cold_monitoring_violations AS (
    SELECT DISTINCT
        'staging_cold_monitoring_mismatch' AS violation,
        signals.city_id
    FROM {{ ref('stg_city_signal_input_v2') }} AS signals
    LEFT JOIN {{ ref('city_signal_monitoring') }} AS monitoring
        ON signals.city_id = monitoring.city_id
    WHERE monitoring.city_id IS NULL
        OR signals.cold_monitored IS DISTINCT FROM monitoring.cold_monitored
)

SELECT * FROM membership_violations
UNION ALL
SELECT * FROM configuration_violations
UNION ALL
SELECT * FROM staging_cold_monitoring_violations
