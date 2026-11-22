#!/usr/bin/env bash
# Backfill warehouse_daily from $1 to $2 (inclusive), one day at a time, oldest first.
# Runs inside the scheduler container (`make backfill FROM=... TO=...`) and stops at the first
# failed day, since a day's build reads every earlier partition.
#
# Each day is one recorded DAG run made by `airflow dags test`, which runs the real tasks and works
# on the paused DAG. Airflow's own `backfill create` does not: the scheduler starts no run of a
# paused DAG, and unpausing it lets catch-up runs write the same DuckDB file in parallel
# (docs/task-management/18-airflow-warehouse-daily.md, Decisions).
set -euo pipefail
from="$1"; to="$2"; dag=warehouse_daily

day="$from"
while [[ ! "$day" > "$to" ]]; do
  echo "[backfill] $day"
  if ! airflow dags test "$dag" "$day" > "/tmp/backfill-$day.log" 2>&1; then
    grep -E "\[(quality_gate|record_run)\]|ERROR|Error" "/tmp/backfill-$day.log" | tail -20 || true
    echo "[backfill] $day failed; full log in the scheduler container at /tmp/backfill-$day.log"
    exit 1
  fi
  grep -E "\[record_run\]" "/tmp/backfill-$day.log" | sed 's/.*\[record_run\]/[record_run]/; s/ \[airflow.*//' || true
  day=$(date -u -d "$day + 1 day" +%F)
done
echo "[backfill] $from to $to: every day passed"
