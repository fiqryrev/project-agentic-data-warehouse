"""warehouse_daily: one day of the warehouse, from source files to ops.run_log (PLAN section 6).

Tasks 1 to 7 and 9 of the plan; 8 (LLM telemetry) arrives with M11.

    1 generate_source  generator writes the day's landing files (deterministic per date)
    2 load_lake        loader replaces the day's partition in data_lake_layer.* of the build file
    3 dbt_build        dbt build --target prod over the whole lake; run_results kept per day
    4 quality_gate     dbt passed, the day landed, no empty mart table
    5 publish_snapshot data_warehouse_layer and data_mart_layer into data/serve/analytics.duckdb
    6 refresh_ontology Auto Ontology restarts on the new file and compiles (skipped when the
                       ontology profile is down)
    7 golden_questions every golden question through the ask client, scored against reference SQL
                       on the snapshot; a wrong answer fails it and lands in the Langfuse queue
                       answer-review (skipped with the refresh, or by conf {"golden": false})
    9 record_run       one row in ops.run_log, whatever happened (runs after a failure too)

One run at a time, oldest day first: every run writes the same DuckDB file, and a day's build
reads every earlier partition. `catchup=True` so days missed while the laptop slept run in order;
the DAG starts paused, so `make up-core` never starts a months-long catch-up by itself.
The repository is mounted at /opt/wh; the project's own environment is /opt/wh-venv (uv).
"""
from __future__ import annotations

import os

import pendulum
from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG
from airflow.task.trigger_rule import TriggerRule

REPO = "/opt/wh"
BUILD_DB = "data/build/dwh.duckdb"
ARTIFACTS = "data/artifacts/{{ ds }}"
PY = "uv run --no-sync python -m"
START = pendulum.parse(os.environ.get("WAREHOUSE_START_DATE", "2026-01-01"), tz="UTC")

with DAG(
    dag_id="warehouse_daily",
    description="Generate, load, build and check one day; record it in ops.run_log",
    schedule="@daily",
    start_date=START,
    catchup=True,
    max_active_runs=1,
    is_paused_upon_creation=True,
    default_args={"depends_on_past": True, "retries": 0, "cwd": REPO},
    tags=["warehouse"],
) as dag:
    generate_source = BashOperator(
        task_id="generate_source",
        bash_command=f"{PY} generator --date {{{{ ds }}}} --out data/landing",
    )
    load_lake = BashOperator(
        task_id="load_lake",
        bash_command=f"{PY} loader --date {{{{ ds }}}} --landing data/landing --db {BUILD_DB}",
    )
    dbt_build = BashOperator(
        task_id="dbt_build",
        bash_command=(
            f"mkdir -p {ARTIFACTS} && rm -f {ARTIFACTS}/run_results.json && cd dbt && "
            "uv run --no-sync dbt build --profiles-dir . --target prod; status=$?; "
            f'cp "$DBT_TARGET_PATH/run_results.json" ../{ARTIFACTS}/ 2>/dev/null; exit $status'
        ),
    )
    quality_gate = BashOperator(
        task_id="quality_gate",
        bash_command=f"{PY} publish.quality_gate --ds {{{{ ds }}}} --db {BUILD_DB} --run-id '{{{{ run_id }}}}'",
    )
    publish_snapshot = BashOperator(
        task_id="publish_snapshot",
        bash_command=f"{PY} publish.snapshot --ds {{{{ ds }}}} --db {BUILD_DB} --run-id '{{{{ run_id }}}}'",
    )
    refresh_ontology = BashOperator(
        task_id="refresh_ontology",
        bash_command=f"{PY} publish.refresh_ontology --ds {{{{ ds }}}} --run-id '{{{{ run_id }}}}'",
        skip_on_exit_code=99,            # ontology profile not running
    )
    # A wrong answer must not hold the next day's data: the data tasks above keep depends_on_past,
    # tasks 7 and 9 do not (a failed record_run would otherwise stall every later run).
    golden_questions = BashOperator(
        task_id="golden_questions",
        bash_command=(f"{PY} llm.golden --ds {{{{ ds }}}} --run-id '{{{{ run_id }}}}' "
                      "--enabled {{ dag_run.conf.get('golden', true) | string | lower }}"),
        skip_on_exit_code=99,            # Auto Ontology not reachable, or disabled for this run
        depends_on_past=False,
    )
    record_run = BashOperator(
        task_id="record_run",
        bash_command=f"{PY} publish.run_recorder --ds {{{{ ds }}}} --db {BUILD_DB} --run-id '{{{{ run_id }}}}'",
        trigger_rule=TriggerRule.ALL_DONE,
        depends_on_past=False,
    )

    (generate_source >> load_lake >> dbt_build >> quality_gate >> publish_snapshot
     >> refresh_ontology >> golden_questions >> record_run)
