"""record_run (DAG task 9): one row per day in ops.run_log, whatever happened (PLAN section 7).

Runs even when an earlier task failed. Reads the day's artifacts (dbt run_results, the quality
gate verdict of this run) and the build file, replaces the day's row in ops.run_log, and exits
1 unless the quality gate of this same run passed, so a failed day stays visible in Airflow.
Snapshot hash and model spend join the row with their tasks (M8, M9).

    uv run python -m publish.run_recorder --ds 2026-01-01 --db data/build/dwh.duckdb --run-id manual
"""
from __future__ import annotations

import argparse
import datetime as dtm
import os
import subprocess
import sys
from pathlib import Path

import duckdb

from publish.artifacts import ARTIFACTS, LAYER_SCHEMAS, day_dir, read_json, dbt_test_counts

DDL = """
create schema if not exists ops;
create table if not exists ops.run_log (
    run_date date primary key,
    dag_run_id varchar,
    git_commit_id varchar,
    dbt_invocation_id varchar,
    lake_day_row_count bigint,
    lake_row_count bigint,
    staging_row_count bigint,
    warehouse_row_count bigint,
    mart_row_count bigint,
    test_pass_count integer,
    test_warn_count integer,
    test_fail_count integer,
    run_status varchar,
    run_problem_description varchar,
    recorded_at timestamp
);
"""


def git_commit() -> str:
    """The commit the code ran from: GIT_SHA (set by `make up-core`), else git, else unknown."""
    if os.environ.get("GIT_SHA"):
        return os.environ["GIT_SHA"]
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def layer_rows(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    out = {}
    for schema in LAYER_SCHEMAS:
        names = [r[0] for r in con.execute(
            "select table_name from information_schema.tables where table_schema = ?", [schema]).fetchall()]
        out[schema] = sum(con.execute(f'select count(*) from "{schema}"."{n}"').fetchone()[0] for n in names)
    return out


def record(db: Path, ds: str, run_id: str, artifacts: Path = ARTIFACTS) -> dict:
    folder = day_dir(ds, artifacts)
    run_results = read_json(folder / "run_results.json")
    gate = read_json(folder / "quality_gate.json")
    if gate is None or gate.get("run_id") != run_id:
        status, problems = "failed", ["the quality gate did not run in this run"]
    else:
        status, problems = gate["status"], gate.get("problems") or []
    tests = dbt_test_counts(run_results)
    db.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db))
    try:
        con.execute(DDL)
        rows = layer_rows(con)
        row = {
            "run_date": ds, "dag_run_id": run_id, "git_commit_id": git_commit(),
            "dbt_invocation_id": ((run_results or {}).get("metadata") or {}).get("invocation_id"),
            "lake_day_row_count": (gate or {}).get("lake_day_rows"),
            "lake_row_count": rows["lake"], "staging_row_count": rows["staging"],
            "warehouse_row_count": rows["warehouse"], "mart_row_count": rows["mart"],
            "test_pass_count": tests["pass"], "test_warn_count": tests["warn"],
            "test_fail_count": tests["fail"], "run_status": status,
            "run_problem_description": "; ".join(problems) or None,
            "recorded_at": dtm.datetime.now(dtm.UTC).replace(tzinfo=None),
        }
        con.execute("begin")
        con.execute("delete from ops.run_log where run_date = ?::date", [ds])
        con.execute(f"insert into ops.run_log ({', '.join(row)}) values ({', '.join('?' * len(row))})",
                    list(row.values()))
        con.execute("commit")
    finally:
        con.close()
    return row


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ds", required=True)
    ap.add_argument("--db", type=Path, required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--artifacts", type=Path, default=ARTIFACTS)
    args = ap.parse_args(argv)
    row = record(args.db, args.ds, args.run_id, args.artifacts)
    print(f"[record_run] {args.ds}: {row['run_status']}; tests {row['test_pass_count']} pass, "
          f"{row['test_warn_count']} warn, {row['test_fail_count']} fail")
    return 0 if row["run_status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
