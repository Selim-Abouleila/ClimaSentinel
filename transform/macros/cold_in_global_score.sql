{% macro cold_in_global_score() %}
    {# Explicit project configuration enables Cold; omission falls back to false. #}
    {% set enabled = var('cold_in_global_score', false) %}
    {% if enabled is not boolean %}
        {{ exceptions.raise_compiler_error(
            "cold_in_global_score must be a YAML boolean (true or false), not a string or number."
        ) }}
    {% endif %}
    {{ return(enabled) }}
{% endmacro %}
