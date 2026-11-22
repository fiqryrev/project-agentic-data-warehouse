select
    run_date, dag_run_id, git_commit_id, run_status, run_problem_description, lake_day_row_count,
    lake_row_count, warehouse_row_count, mart_row_count, test_pass_count, test_warn_count,
    test_fail_count, snapshot_hash_code, ontology_refresh_status, golden_status,
    golden_question_count, golden_wrong_count, golden_refused_count, telemetry_status, recorded_at,
    {{ dbt_audit_columns() }}
from {{ ref('staging__airflow__run_log') }}
