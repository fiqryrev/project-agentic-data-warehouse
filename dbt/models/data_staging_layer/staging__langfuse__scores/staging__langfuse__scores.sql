select
    score_id,
    trace_id,
    observation_id,
    name as score_name,
    data_type as score_data_type,
    value as score_value_quantity,
    string_value as score_text_description,
    comment as score_comment_description,
    source as score_source_type,
    coalesce(author_user_id, 'api') as author_user_id,
    config_id as score_config_id,
    queue_id as annotation_queue_id,
    scored_at,
    updated_at as score_updated_at,
    _dt
from {{ source('lake', 'langfuse__scores') }}
qualify row_number() over (partition by score_id order by updated_at desc nulls last, _dt desc) = 1
