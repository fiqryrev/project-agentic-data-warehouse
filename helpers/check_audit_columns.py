#!/usr/bin/env python3
"""check_audit_columns: every lake and warehouse row can say where it came from (PLAN section 7).

- Lake: every table in schema `lake` carries `_dt`, `_source_file`, `_loaded_at`, `_batch_id`,
  and every table declared in source `lake` exists. Read from a DuckDB file: by default a
  fresh one, built from one generated day with the project's own generator and loader (as
  check_duckdb_compat does); `--db <file>` reads an existing build instead.
- Staging: every model passes `_dt` through, so a warehouse row can be traced to its partition.
- Warehouse: every model outputs `_dbt_invocation_id` and `_dbt_updated_at` (read statically
  from the SQL, see helpers/dbtlib.py; the `dbt_audit_columns()` macro adds both).
"""
from __future__ import annotations

import argparse
import datetime as dtm
import sys
import tempfile
from pathlib import Path

import duckdb

try:
    from helpers import dbtlib
    from helpers.govlib import report
except ModuleNotFoundError:
    import dbtlib  # type: ignore
    from govlib import report  # type: ignore

NAME = "check_audit_columns"
LAKE_AUDIT = ("_dt", "_source_file", "_loaded_at", "_batch_id")
WAREHOUSE_AUDIT = ("_dbt_invocation_id", "_dbt_updated_at")
STAGING_AUDIT = ("_dt",)
PROBE_DATE = "2026-01-01"   # the epoch: every source writes on its first day


def lake_columns(con: duckdb.DuckDBPyConnection) -> dict[str, set[str]]:
    rows = con.execute("select table_name, column_name from information_schema.columns "
                       "where table_schema = 'lake'").fetchall()
    out: dict[str, set[str]] = {}
    for table, column in rows:
        out.setdefault(table, set()).add(column)
    return out


def lake_errors(tables: dict[str, set[str]], declared: set[str]) -> list[str]:
    errors = []
    if not tables:
        return ["the lake has no tables"]
    for table, cols in sorted(tables.items()):
        missing = [c for c in LAKE_AUDIT if c not in cols]
        if missing:
            errors.append(f"lake.{table}: missing audit columns {', '.join(missing)}")
    for table in sorted(declared - set(tables)):
        errors.append(f"source('lake', '{table}') is declared but lake.{table} does not exist")
    return errors


def model_errors(models: list[dbtlib.Model]) -> list[str]:
    errors = []
    for m in models:
        need = {"warehouse": WAREHOUSE_AUDIT, "staging": STAGING_AUDIT}.get(m.layer or "")
        if not need:
            continue
        if m.columns is None:
            errors.append(f"{m.path}: cannot read the output columns ({m.parse_error})")
            continue
        missing = [c for c in need if c not in m.columns]
        if missing:
            hint = " (add {{ dbt_audit_columns() }})" if m.layer == "warehouse" else ""
            errors.append(f"{m.path}: {m.layer} model does not output {', '.join(missing)}{hint}")
    return errors


def build_lake(db: Path) -> None:
    from generator.write import write_day
    from loader.load import load_day

    landing = db.parent / "landing"
    day = dtm.date.fromisoformat(PROBE_DATE)
    write_day(42, day, landing)
    con = duckdb.connect(str(db))
    try:
        load_day(con, landing, day)
    finally:
        con.close()


def check(con: duckdb.DuckDBPyConnection, project: Path = dbtlib.DBT_DIR) -> list[str]:
    declared = dbtlib.load_sources(project).get("lake", set())
    return lake_errors(lake_columns(con), declared) + model_errors(dbtlib.load_models(project))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", help="an existing DuckDB build to read the lake from")
    ap.add_argument("--project", default=str(dbtlib.DBT_DIR))
    args = ap.parse_args(argv)
    project = Path(args.project)
    if args.db:
        con = duckdb.connect(args.db, read_only=True)
        try:
            return report(NAME, check(con, project))
        finally:
            con.close()
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "audit.duckdb"
        build_lake(db)
        con = duckdb.connect(str(db), read_only=True)
        try:
            return report(NAME, check(con, project))
        finally:
            con.close()


if __name__ == "__main__":
    sys.exit(main())
