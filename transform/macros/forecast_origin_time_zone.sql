{% macro forecast_origin_time_zone(city_id_expression) -%}
    CASE {{ city_id_expression }}
        WHEN 'paris_fr' THEN 'Europe/Paris'
        WHEN 'london_gb' THEN 'Europe/London'
        WHEN 'madrid_es' THEN 'Europe/Madrid'
        WHEN 'berlin_de' THEN 'Europe/Berlin'
        WHEN 'rome_it' THEN 'Europe/Rome'
        WHEN 'amsterdam_nl' THEN 'Europe/Amsterdam'
        WHEN 'athens_gr' THEN 'Europe/Athens'
        WHEN 'warsaw_pl' THEN 'Europe/Warsaw'
        WHEN 'lisbon_pt' THEN 'Europe/Lisbon'
        WHEN 'stockholm_se' THEN 'Europe/Stockholm'
        ELSE ERROR(
            CONCAT(
                'No IANA forecast timezone configured for city_id: ',
                COALESCE(CAST({{ city_id_expression }} AS STRING), '<NULL>')
            )
        )
    END
{%- endmacro %}
