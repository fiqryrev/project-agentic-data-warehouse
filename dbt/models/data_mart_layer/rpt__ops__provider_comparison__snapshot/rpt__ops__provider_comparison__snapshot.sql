-- One row per comparison run and candidate (make compare-providers, PLAN 8.6).
with runs as (
    select
        comparison_run_code,
        candidate_name,
        any_value(reasoning_model_name) as reasoning_model_name,
        any_value(non_reasoning_model_name) as non_reasoning_model_name,
        min(answer_started_at) as run_started_at,
        max(answer_finished_at) as run_finished_at,
        count(*) as question_count,
        count(*) filter (where golden_verdict_status = 'exact_match') as exact_match_count,
        count(*) filter (where golden_verdict_status = 'within_tolerance') as within_tolerance_count,
        count(*) filter (where golden_verdict_status = 'wrong') as wrong_count,
        count(*) filter (where golden_verdict_status = 'refused') as refused_count,
        sum(coalesce(linked_cost_usd, 0)) as linked_cost_usd,
        sum(coalesce(linked_call_count, 0)) as linked_call_count
    from {{ ref('fact__ops__answer') }}
    where comparison_run_code is not null
    group by comparison_run_code, candidate_name
),
calls as (
    select
        r.comparison_run_code,
        r.candidate_name,
        quantile_cont(c.call_duration_ms, 0.95) as p95_latency_ms,
        any_value(c.provider_name) as provider_name,
        any_value(c.model_name) as model_name
    from runs r
    join {{ ref('fact__ops__llm_call') }} c
        on c.model_alias_name in (r.reasoning_model_name, r.non_reasoning_model_name)
        and c.call_started_at between r.run_started_at and r.run_finished_at
    group by r.comparison_run_code, r.candidate_name
)
select
    r.comparison_run_code,
    r.candidate_name,
    r.reasoning_model_name,
    r.non_reasoning_model_name,
    c.provider_name,
    c.model_name,
    r.run_started_at,
    r.question_count,
    r.exact_match_count,
    r.within_tolerance_count,
    r.wrong_count,
    r.refused_count,
    100.0 * (r.exact_match_count + r.within_tolerance_count) / r.question_count as accuracy_pct,
    r.linked_cost_usd,
    case when r.exact_match_count + r.within_tolerance_count > 0
        then r.linked_cost_usd / (r.exact_match_count + r.within_tolerance_count) end as cost_per_correct_usd,
    r.linked_call_count,
    c.p95_latency_ms,
    {{ dbt_audit_columns() }}
from runs r
left join calls c using (comparison_run_code, candidate_name)
