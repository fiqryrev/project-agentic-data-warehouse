select
    run_date, run_status, run_problem_description, test_pass_count, test_warn_count, test_fail_count,
    lake_day_row_count, warehouse_row_count, mart_row_count, ontology_refresh_status, golden_status,
    golden_question_count, golden_wrong_count, golden_refused_count, recorded_at,
    {{ dbt_audit_columns() }}
from {{ ref('fact__ops__pipeline_run') }}
