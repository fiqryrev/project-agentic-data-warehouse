select
    trace_id, session_id, answer_started_at, answer_started_at::date as answer_date, question_description,
    answer_description, answer_sql_description, answer_row_count, answer_error_description,
    snapshot_hash_code, golden_id, golden_verdict_status, is_sql_consistent, is_golden,
    linked_cost_usd, linked_call_count, link_method_type,
    {{ dbt_audit_columns() }}
from {{ ref('staging__langfuse__answers') }}
