{# Use the configured schema as is (data_staging_layer, data_warehouse_layer, data_mart_layer), not <target>_<schema>. #}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {{ custom_schema_name if custom_schema_name else target.schema }}
{%- endmacro %}
