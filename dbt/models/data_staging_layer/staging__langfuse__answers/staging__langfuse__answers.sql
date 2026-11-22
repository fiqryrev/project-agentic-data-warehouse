select
    trace_id,
    session_id,
    tags as answer_tags_description,
    started_at as answer_started_at,
    question as question_description,
    answer as answer_description,
    sql as answer_sql_description,
    row_count as answer_row_count,
    error as answer_error_description,
    snapshot_hash as snapshot_hash_code,
    golden_id,
    golden_verdict as golden_verdict_status,
    sql_consistent as is_sql_consistent,
    coalesce(golden_id is not null, false) as is_golden,
    linked_cost_usd,
    linked_call_count,
    link_method as link_method_type,
    _dt
from {{ source('lake', 'langfuse__answers') }}
qualify row_number() over (partition by trace_id order by _dt desc, _loaded_at desc) = 1
