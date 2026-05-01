-- Override dbt's default schema name generation.
-- Without this, dbt prepends the target dataset to the custom schema,
-- producing "stg_stg" instead of just "stg".
-- With this macro, models with +schema: stg land in the "stg" dataset directly.

{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
