select
    request_id,
    call_type,
    coalesce(caller_alias, 'none') as caller_name,
    coalesce(nullif(model_group, ''), 'none') as model_alias_name,
    model as model_name,
    provider as provider_name,
    status as call_status,
    coalesce(nullif(regexp_extract(job_tags, '"job:([a-z0-9_-]+)"', 1), ''), 'none') as job_name,
    started_at as call_started_at,
    ended_at as call_ended_at,
    duration_ms as call_duration_ms,
    coalesce(prompt_tokens, 0) as prompt_token_count,
    coalesce(completion_tokens, 0) as completion_token_count,
    coalesce(total_tokens, 0) as total_token_count,
    coalesce(spend_usd, 0) as spend_usd,
    coalesce(lower(cache_hit) = 'true', false) as is_cache_hit,
    _dt
from {{ source('lake', 'gateway__spend_logs') }}
qualify row_number() over (partition by request_id order by _dt desc, _loaded_at desc) = 1
