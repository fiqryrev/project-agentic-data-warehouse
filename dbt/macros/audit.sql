{# Audit columns on every warehouse row (PLAN section 7). #}
{% macro dbt_audit_columns() -%}
    '{{ invocation_id }}' as _dbt_invocation_id,
    current_timestamp::timestamp as _dbt_updated_at
{%- endmacro %}

{# Title case for names the source writes in all upper or all lower case. #}
{% macro title_case(col) -%}
    list_aggr(
        list_transform(string_split(lower({{ col }}), ' '), w -> upper(w[1]) || w[2:]),
        'string_agg', ' '
    )
{%- endmacro %}

{# The numeric part of a ledger key such as C-0001234 or ORD-12345. #}
{% macro key_number(col, prefix) -%}
    cast(replace({{ col }}, '{{ prefix }}', '') as bigint)
{%- endmacro %}
