select
    call_date,
    caller_name,
    job_name,
    coalesce(model_alias_name, 'none') as model_alias_name,
    coalesce(provider_name, 'none') as provider_name,
    coalesce(model_name, 'none') as model_name,
    count(*) as call_count,
    sum(prompt_token_count) as prompt_token_count,
    sum(completion_token_count) as completion_token_count,
    sum(spend_usd) as spend_usd,
    {{ dbt_audit_columns() }}
from {{ ref('fact__ops__llm_call') }}
group by call_date, caller_name, job_name, coalesce(model_alias_name, 'none'),
    coalesce(provider_name, 'none'), coalesce(model_name, 'none')
