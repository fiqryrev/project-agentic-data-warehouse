{# Use the configured schema as is (staging, warehouse, mart), not <target>_<schema>. #}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {{ custom_schema_name if custom_schema_name else target.schema }}
{%- endmacro %}
