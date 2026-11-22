select
    trace_id,
    author_user_id as labeler_user_id,
    max(case when score_name = 'verdict' then score_text_description end) as label_verdict_status,
    max(case when score_name = 'reasoning_ok' then score_text_description end) as reasoning_ok_status,
    max(case when score_name = 'correct_answer' then score_text_description end) as correct_answer_description,
    max(case when score_name = 'correct_sql' then score_text_description end) as correct_sql_description,
    max(case when score_name = 'note' then score_text_description end) as label_note_description,
    max(score_source_type) as label_source_type,
    max(scored_at) as labeled_at,
    max(scored_at)::date as labeled_date,
    {{ dbt_audit_columns() }}
from {{ ref('staging__langfuse__scores') }}
where score_name in ('verdict', 'reasoning_ok', 'correct_answer', 'correct_sql', 'note')
group by trace_id, author_user_id
