"""quality_gate (DAG task 4): is the day's build good enough to publish?

Fails (exit 1) when:
- dbt's run_results for the day is missing, or any node errored, failed or was skipped
  (warnings pass: they are known defects the tests are told to tolerate);
- the lake holds no row for the day (`_dt = ds`) in any table;
- a mart table is empty (marts aggregate every day there is data).
An empty warehouse table is reported but passes: early days have no refunds yet.
Writes data/artifacts/<ds>/quality_gate.json with the run id, so the run recorder never reads a
verdict left by an earlier run of the same day.

    uv run python -m publish.quality_gate --ds 2026-01-01 --db data/build/dwh.duckdb --run-id manual
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb

from publish.artifacts import ARTIFACTS, day_dir, failed_nodes, read_json, dbt_test_counts, write_json


def table_rows(con: duckdb.DuckDBPyConnection, schema: str) -> dict[str, int]:
    names = [r[0] for r in con.execute(
        "select table_name from information_schema.tables where table_schema = ? "
        "order by table_name", [schema]).fetchall()]
    return {n: con.execute(f'select count(*) from "{schema}"."{n}"').fetchone()[0] for n in names}


def lake_day_rows(con: duckdb.DuckDBPyConnection, ds: str) -> int:
    total = 0
    for name in table_rows(con, "lake"):
        total += con.execute(f'select count(*) from lake."{name}" where _dt = ?::date', [ds]).fetchone()[0]
    return total


def evaluate(db: Path, ds: str, run_results: dict | None) -> tuple[list[str], dict]:
    problems = []
    counts = dbt_test_counts(run_results)
    if run_results is None:
        problems.append("no dbt run_results for the day")
    elif bad := failed_nodes(run_results):
        problems.append(f"{len(bad)} dbt node(s) did not pass: " + ", ".join(bad[:10]))
    con = duckdb.connect(str(db), read_only=True)
    try:
        day = lake_day_rows(con, ds)
        if day == 0:
            problems.append(f"the lake has no row for {ds}")
        empty_marts = [f"mart.{t}" for t, n in table_rows(con, "mart").items() if n == 0]
        if empty_marts:
            problems.append("empty mart tables: " + ", ".join(empty_marts))
        empty_warehouse = [f"warehouse.{t}" for t, n in table_rows(con, "warehouse").items() if n == 0]
    finally:
        con.close()
    return problems, {"lake_day_rows": day, "tests": counts, "empty_warehouse_tables": empty_warehouse}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ds", required=True)
    ap.add_argument("--db", type=Path, required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--artifacts", type=Path, default=ARTIFACTS)
    args = ap.parse_args(argv)
    folder = day_dir(args.ds, args.artifacts)
    problems, facts = evaluate(args.db, args.ds, read_json(folder / "run_results.json"))
    status = "failed" if problems else "passed"
    write_json(folder / "quality_gate.json",
               {"ds": args.ds, "run_id": args.run_id, "status": status, "problems": problems, **facts})
    for p in problems:
        print(f"[quality_gate] {p}")
    if facts["empty_warehouse_tables"]:
        print("[quality_gate] empty (allowed): " + ", ".join(facts["empty_warehouse_tables"]))
    print(f"[quality_gate] {args.ds}: {status}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
