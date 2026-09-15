{% macro cold_in_global_score() %}
    {# Keep the live five-factor contract until the application cutover. #}
    {% set enabled = var('cold_in_global_score', false) %}
    {% if enabled is not boolean %}
        {{ exceptions.raise_compiler_error(
            "cold_in_global_score must be a YAML boolean (true or false), not a string or number."
        ) }}
    {% endif %}
    {{ return(enabled) }}
{% endmacro %}
