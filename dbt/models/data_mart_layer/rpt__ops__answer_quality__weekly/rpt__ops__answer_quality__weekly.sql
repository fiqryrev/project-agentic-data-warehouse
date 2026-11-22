with answers as (
    select date_trunc('week', answer_date)::date as week_start_date,
        count(*) filter (where is_golden) as golden_answer_count,
        count(*) filter (where golden_verdict_status = 'exact_match') as exact_match_count,
        count(*) filter (where golden_verdict_status = 'within_tolerance') as within_tolerance_count,
        count(*) filter (where golden_verdict_status = 'wrong') as wrong_count,
        count(*) filter (where golden_verdict_status = 'refused') as refused_count,
        count(*) filter (where is_sql_consistent = false) as inconsistent_sql_count
    from {{ ref('fact__ops__answer') }}
    group by date_trunc('week', answer_date)::date
),
labels as (
    select date_trunc('week', labeled_date)::date as week_start_date,
        count(*) as label_count,
        count(*) filter (where label_verdict_status = 'correct') as label_correct_count,
        count(*) filter (where label_verdict_status = 'wrong_number') as label_wrong_number_count,
        count(*) filter (where label_verdict_status = 'wrong_definition') as label_wrong_definition_count,
        count(*) filter (where label_verdict_status = 'wrong_grain') as label_wrong_grain_count,
        count(*) filter (where label_verdict_status = 'wrong_filter') as label_wrong_filter_count,
        count(*) filter (where label_verdict_status = 'should_have_refused') as label_should_have_refused_count,
        count(*) filter (where label_verdict_status = 'refused_wrongly') as label_refused_wrongly_count,
        count(*) filter (where reasoning_ok_status = 'yes') as reasoning_ok_count,
        count(*) filter (where reasoning_ok_status is not null) as reasoning_rated_count
    from {{ ref('fact__ops__answer_label') }}
    group by date_trunc('week', labeled_date)::date
)
select
    coalesce(a.week_start_date, l.week_start_date) as week_start_date,
    coalesce(a.golden_answer_count, 0) as golden_answer_count,
    coalesce(a.exact_match_count, 0) as exact_match_count,
    coalesce(a.within_tolerance_count, 0) as within_tolerance_count,
    coalesce(a.wrong_count, 0) as wrong_count,
    coalesce(a.refused_count, 0) as refused_count,
    case when a.golden_answer_count > 0
        then 100.0 * (a.exact_match_count + a.within_tolerance_count) / a.golden_answer_count end as golden_accuracy_pct,
    coalesce(a.inconsistent_sql_count, 0) as inconsistent_sql_count,
    coalesce(l.label_count, 0) as label_count,
    coalesce(l.label_correct_count, 0) as label_correct_count,
    coalesce(l.label_wrong_number_count, 0) as label_wrong_number_count,
    coalesce(l.label_wrong_definition_count, 0) as label_wrong_definition_count,
    coalesce(l.label_wrong_grain_count, 0) as label_wrong_grain_count,
    coalesce(l.label_wrong_filter_count, 0) as label_wrong_filter_count,
    coalesce(l.label_should_have_refused_count, 0) as label_should_have_refused_count,
    coalesce(l.label_refused_wrongly_count, 0) as label_refused_wrongly_count,
    case when l.reasoning_rated_count > 0
        then 100.0 * l.reasoning_ok_count / l.reasoning_rated_count end as reasoning_ok_share_pct,
    {{ dbt_audit_columns() }}
from answers a
full outer join labels l on a.week_start_date = l.week_start_date
