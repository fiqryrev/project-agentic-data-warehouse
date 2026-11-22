select
    request_id, call_type, caller_name, model_alias_name, model_name, provider_name, call_status,
    job_name, call_started_at, call_ended_at, call_started_at::date as call_date, call_duration_ms,
    prompt_token_count, completion_token_count, total_token_count, spend_usd, is_cache_hit,
    {{ dbt_audit_columns() }}
from {{ ref('staging__gateway__spend_logs') }}
