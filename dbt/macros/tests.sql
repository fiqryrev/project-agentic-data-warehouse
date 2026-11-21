{# No two rows share the same values in these columns. #}
{% test unique_combination(model, columns) %}
select {{ columns | join(', ') }}, count(*) as n
from {{ model }}
group by {{ columns | join(', ') }}
having count(*) > 1
{% endtest %}

{# History rows of one key never overlap, and each key has exactly one current row. #}
{% test scd2_valid(model, key) %}
with ordered as (
    select
        {{ key }} as k, valid_from, valid_to, is_current,
        lead(valid_from) over (partition by {{ key }} order by valid_from) as next_from
    from {{ model }}
)
select k, valid_from, 'overlap or gap' as problem from ordered
where next_from is not null and valid_to is distinct from next_from
union all
select k, null, 'current flag disagrees with valid_to' from ordered
where is_current <> (valid_to is null)
union all
select k, null, 'not exactly one current row' from ordered
group by k having sum(case when is_current then 1 else 0 end) <> 1
{% endtest %}
