select
    call_date,
    coalesce(model_alias_name, 'none') as model_alias_name,
    count(*) as call_count,
    quantile_cont(call_duration_ms, 0.5) as p50_latency_ms,
    quantile_cont(call_duration_ms, 0.95) as p95_latency_ms,
    count(*) filter (where call_status <> 'success') as error_count,
    100.0 * count(*) filter (where call_status <> 'success') / count(*) as error_rate_pct,
    {{ dbt_audit_columns() }}
from {{ ref('fact__ops__llm_call') }}
group by call_date, coalesce(model_alias_name, 'none')
