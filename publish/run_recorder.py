"""record_run (DAG task 9): one row per day in ops.run_log, whatever happened (PLAN section 7).

Runs even when an earlier task failed. Reads the day's artifacts (dbt run_results, and this run's
quality gate, snapshot and ontology refresh) and the build file, replaces the day's row in
ops.run_log, and exits 1 unless this run's gate passed, its snapshot was published, and the
ontology refresh passed or was skipped (profile down), so a failed day stays visible in Airflow.
Model spend joins the row with the telemetry task (M11).

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
alter table ops.run_log add column if not exists snapshot_hash_code varchar;
alter table ops.run_log add column if not exists ontology_refresh_status varchar;
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
    for layer, schema in LAYER_SCHEMAS.items():
        names = [r[0] for r in con.execute(
            "select table_name from information_schema.tables where table_schema = ?", [schema]).fetchall()]
        out[layer] = sum(con.execute(f'select count(*) from "{schema}"."{n}"').fetchone()[0] for n in names)
    return out


def this_run(doc: dict | None, run_id: str) -> dict | None:
    """The artifact if this run wrote it; a file left by an earlier run of the day counts as missing."""
    return doc if doc is not None and doc.get("run_id") == run_id else None


def record(db: Path, ds: str, run_id: str, artifacts: Path = ARTIFACTS) -> dict:
    folder = day_dir(ds, artifacts)
    run_results = read_json(folder / "run_results.json")
    gate = this_run(read_json(folder / "quality_gate.json"), run_id)
    snapshot = this_run(read_json(folder / "snapshot.json"), run_id)
    refresh = this_run(read_json(folder / "refresh.json"), run_id)
    if gate is None:
        status, problems = "failed", ["the quality gate did not run in this run"]
    else:
        status, problems = gate["status"], list(gate.get("problems") or [])
    if status == "passed" and snapshot is None:
        status, problems = "failed", problems + ["the snapshot was not published in this run"]
    # refresh_ontology reports every outcome, skipped included; no report after a published
    # snapshot means it crashed or never ran, which must not pass as a skip (review on #23).
    if refresh is None:
        refresh_status = "missing" if snapshot is not None else "not run"
    else:
        refresh_status = refresh.get("status", "missing")
    if refresh_status == "failed":
        status = "failed"
        problems.append(f"ontology refresh failed: {refresh.get('error')}")
    elif refresh_status == "missing" and status == "passed":
        status = "failed"
        problems.append("ontology refresh did not report in this run")
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
            "snapshot_hash_code": (snapshot or {}).get("snapshot_hash"),
            "ontology_refresh_status": refresh_status,
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
