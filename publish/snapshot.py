"""publish_snapshot (DAG task 5): the serving file Auto Ontology reads (PLAN D2 and section 6).

1. Copy the build file into a temporary file next to the serving file with `COPY FROM DATABASE`
   (keeps table and column comments, M0), then drop every schema but `data_warehouse_layer` and `data_mart_layer`:
   Auto Ontology sees those two only (PLAN section 4).
2. Check every table's row count against the build file.
3. Keep it as data/serve/analytics-<ds>.duckdb and replace data/serve/analytics.duckdb with an
   atomic rename (a reader holding the old file keeps it until it reopens). Keep the last KEEP
   dated copies.
4. Write data/artifacts/<ds>/snapshot.json: run id, file hash, schema hash, tables and rows.

    uv run python -m publish.snapshot --ds 2026-01-07 --db data/build/dwh.duckdb --run-id manual
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sys
from pathlib import Path

import duckdb

from publish.artifacts import ARTIFACTS, day_dir, write_json

SERVE = Path("data/serve")
SERVE_NAME = "analytics"          # the catalog name readers see is the file name
SERVED_SCHEMAS = ("data_warehouse_layer", "data_mart_layer")
KEEP = 7


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def tables(con: duckdb.DuckDBPyConnection, catalog: str) -> dict[str, int]:
    names = con.execute(
        "select schema_name, table_name from duckdb_tables() where database_name = ? "
        "and schema_name in (select unnest(?)) order by 1, 2", [catalog, list(SERVED_SCHEMAS)]).fetchall()
    return {f"{s}.{t}": con.execute(f'select count(*) from "{catalog}"."{s}"."{t}"').fetchone()[0]  # noqa: S608  identifiers only; values bound with ?
            for s, t in names}


def schema_hash(con: duckdb.DuckDBPyConnection, catalog: str) -> str:
    """Hash of every served table's columns and types: a change means Auto Ontology must recompile."""
    rows = con.execute(
        "select schema_name, table_name, column_name, data_type from duckdb_columns() "
        "where database_name = ? and schema_name in (select unnest(?)) order by 1, 2, column_index",
        [catalog, list(SERVED_SCHEMAS)]).fetchall()
    return hashlib.sha256(repr(rows).encode()).hexdigest()


def build_snapshot(build_db: Path, out: Path) -> dict:
    """Write the served schemas of build_db to out; return its tables, rows and hashes."""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.unlink(missing_ok=True)
    con = duckdb.connect(str(out))
    try:
        catalog = con.execute("select current_database()").fetchone()[0]
        con.execute(f"attach '{build_db}' as build (read_only)")
        con.execute(f'copy from database build to "{catalog}"')
        kept = set(SERVED_SCHEMAS) | {"main"}
        for (schema,) in con.execute(
                "select schema_name from duckdb_schemas() where database_name = ? "
                "and not internal", [catalog]).fetchall():
            if schema not in kept:
                con.execute(f'drop schema "{catalog}"."{schema}" cascade')
        served, source = tables(con, catalog), tables(con, "build")
        if served != source:
            diff = {k: (source.get(k), served.get(k)) for k in set(source) | set(served)
                    if source.get(k) != served.get(k)}
            raise SystemExit(f"[publish_snapshot] row counts differ from the build file: {diff}")
        if not served:
            raise SystemExit("[publish_snapshot] the build file has no warehouse or mart table")
        shash = schema_hash(con, catalog)
        con.execute("detach build")
        con.execute("checkpoint")
    finally:
        con.close()
    return {"tables": served, "schema_hash": shash}


def publish(build_db: Path, ds: str, run_id: str, serve: Path = SERVE,
            artifacts: Path = ARTIFACTS, keep: int = KEEP) -> dict:
    tmp = serve / f".{SERVE_NAME}-{ds}.tmp.duckdb"
    facts = build_snapshot(build_db, tmp)
    dated = serve / f"{SERVE_NAME}-{ds}.duckdb"
    os.replace(tmp, dated)
    digest = file_hash(dated)
    staged = serve / f".{SERVE_NAME}.next.duckdb"
    shutil.copyfile(dated, staged)
    os.replace(staged, serve / f"{SERVE_NAME}.duckdb")     # atomic: readers see old or new
    # Keep the newest `keep` dated copies, and always the one just written: a backfill of an old
    # day must not delete its own snapshot (review on #23).
    others = sorted(p for p in serve.glob(f"{SERVE_NAME}-????-??-??.duckdb") if p != dated)
    for old in others[:max(0, len(others) - (keep - 1))]:
        old.unlink()
    doc = {"ds": ds, "run_id": run_id, "path": str(serve / f"{SERVE_NAME}.duckdb"),
           "snapshot_hash": digest, **facts}
    write_json(day_dir(ds, artifacts) / "snapshot.json", doc)
    return doc


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ds", required=True)
    ap.add_argument("--db", type=Path, required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--serve", type=Path, default=SERVE)
    ap.add_argument("--artifacts", type=Path, default=ARTIFACTS)
    args = ap.parse_args(argv)
    doc = publish(args.db, args.ds, args.run_id, args.serve, args.artifacts)
    print(f"[publish_snapshot] {args.ds}: {len(doc['tables'])} tables, "
          f"{sum(doc['tables'].values()):,} rows -> {doc['path']} (sha256 {doc['snapshot_hash'][:12]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
