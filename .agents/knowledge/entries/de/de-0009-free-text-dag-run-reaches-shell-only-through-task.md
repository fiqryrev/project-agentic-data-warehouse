---
id: de-0009
title: Free text from a DAG run reaches the shell only through the task environment
tags: [airflow, security, bash, jinja, conf, run_id, shell-injection, dag]
paths: [airflow/dags/warehouse_daily.py, tests/pipeline/test_airflow_files.py]
status: active
created: 2026-11-23
last_verified: 2026-11-23
evidence:
  - "airflow/dags/warehouse_daily.py::RUN_ENV = {\"RUN_ID\": \"{{ run_id }}\"}"
  - tests/pipeline/test_airflow_files.py::test_no_free_text_template_reaches_a_command_line
  - docs/task-management/40-security-phase-1.md::S1
supersedes: []
---

## Rule

A `BashOperator`'s `bash_command` may template `{{ ds }}` and constants only. Anything chosen by
whoever triggers a run (`dag_run.conf`, `run_id`) goes into `env=` (with `append_env=True`) and
is read in the command as a double-quoted variable (`"$RUN_ID"`). A conf flag is rendered so it
can only yield fixed words (`true` or `false`).

## Why

Airflow renders the template into a string that bash then parses, so text in a conf value or a
run id becomes shell syntax. The UI here gives every visitor admin, so anything that reaches
127.0.0.1:8080 could trigger a run with `x; <command>` and run it in the scheduler, which also
held every secret (security review 2026-11-23, S1 and S2).

## How to apply

Add the value to the task's `env=` dict, keep `append_env=True` (without it the task loses the
container's environment), reference it as `"$NAME"`, and let the Python side parse it again.
`test_no_free_text_template_reaches_a_command_line` fails on any `dag_run`, `conf` or `run_id`
inside a `bash_command`.

## Example

`golden_questions`: `--enabled "$GOLDEN_ENABLED"` with
`GOLDEN_ENABLED = {{ 'false' if (dag_run.conf.get('golden', true) | string | lower) in ('false', '0', 'no') else 'true' }}`;
a conf of `x; touch /tmp/pwned` renders to `true`.
