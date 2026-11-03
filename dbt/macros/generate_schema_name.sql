{# Build models in the schema they ask for (staging, intermediate, marts), not "<target>_<schema>". #}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {{ custom_schema_name if custom_schema_name is not none else target.schema }}
{%- endmacro %}
