"""Load landing partitions into the `data_lake_layer` schema (PLAN sections 4, 6 and 7).

One table per source table, `data_lake_layer.<source>__<table>`, holding every source column plus four
audit columns:
    _dt           partition date the row arrived in
    _source_file  landing file, relative to the landing folder
    _loaded_at    when this load ran (UTC); the only value that changes between reloads
    _batch_id     <date>-<first 12 hex of the manifest's SHA-256>; same input, same id

A day loads in one transaction: for each table, delete the rows of that `_dt`, insert the
partition, and check the row count against the manifest. Loading a day twice leaves the
counts unchanged. Before anything is written, every file's SHA-256 must match the manifest.
A Parquet file whose columns differ from the lake table stops the load (no silent ALTER).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from pathlib import Path

import duckdb

SCHEMA = "data_lake_layer"
AUDIT_COLUMNS = {
    "_dt": ("DATE", "Partition date the row arrived in (landing dt=)."),
    "_source_file": ("VARCHAR", "Landing file the row came from, relative to the landing folder."),
    "_loaded_at": ("TIMESTAMP", "When the load that wrote this row ran, UTC."),
    "_batch_id": ("VARCHAR", "Load batch: <date>-<first 12 hex of the manifest SHA-256>."),
}
NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class LoadError(RuntimeError):
    """The landing partition cannot be loaded as it is."""


def manifest_file(landing: Path, day: dt.date) -> Path:
    return landing / "_manifest" / f"dt={day.isoformat()}" / "manifest.json"


def partition_file(landing: Path, source: str, table: str, day: dt.date) -> Path:
    return landing / source / table / f"dt={day.isoformat()}" / "part-0.parquet"


def lake_table(source: str, table: str) -> str:
    for part in (source, table):
        if not NAME_RE.match(part):
            raise LoadError(f"unsafe source or table name: {part!r}")
    return f"{source}__{table}"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sql_str(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def read_manifest(landing: Path, day: dt.date) -> tuple[dict, str]:
    path = manifest_file(landing, day)
    if not path.is_file():
        raise LoadError(f"no manifest for {day}: {path.relative_to(landing)} is missing")
    raw = path.read_bytes()
    manifest = json.loads(raw)
    if manifest.get("date") != day.isoformat():
        raise LoadError(f"manifest {path.relative_to(landing)} is for {manifest.get('date')}")
    return manifest, f"{day.isoformat()}-{hashlib.sha256(raw).hexdigest()[:12]}"


def verify_files(landing: Path, day: dt.date, manifest: dict) -> list[tuple[str, str, Path, int]]:
    """Check every file named in the manifest exists and matches its checksum."""
    out = []
    for key, meta in sorted(manifest["tables"].items()):
        source, _, table = key.partition(".")
        path = partition_file(landing, source, table, day)
        if not path.is_file():
            raise LoadError(f"{key}: {path.relative_to(landing)} is missing")
        if _sha256(path) != meta["sha256"]:
            raise LoadError(f"{key}: checksum of {path.relative_to(landing)} does not match the manifest")
        out.append((source, table, path, int(meta["rows"])))
    return out


def _columns(con, select_sql: str) -> list[tuple[str, str]]:
    return [(r[0], r[1]) for r in con.execute(f"DESCRIBE {select_sql}").fetchall()]


def _table_columns(con, name: str) -> list[tuple[str, str]] | None:
    rows = con.execute(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_schema = ? AND table_name = ? ORDER BY ordinal_position",
        [SCHEMA, name],
    ).fetchall()
    return [(r[0], r[1]) for r in rows] or None


def _create(con, name: str, src: str) -> None:
    audit = ", ".join(f"NULL::{typ} AS {col}" for col, (typ, _) in AUDIT_COLUMNS.items())
    con.execute(f"CREATE TABLE {SCHEMA}.{name} AS SELECT *, {audit} FROM {src} LIMIT 0")  # noqa: S608  identifiers only; values bound with ?
    con.execute(f"COMMENT ON TABLE {SCHEMA}.{name} IS "
                f"{_sql_str('Lake copy of the landing source table; append-only by _dt.')}")
    for col, (_, text) in AUDIT_COLUMNS.items():
        con.execute(f"COMMENT ON COLUMN {SCHEMA}.{name}.{col} IS {_sql_str(text)}")


def load_day(con: duckdb.DuckDBPyConnection, landing: Path, day: dt.date,
             loaded_at: dt.datetime | None = None) -> dict[str, int]:
    """Load one partition date. Returns {lake table: rows for that date}."""
    landing = Path(landing)
    manifest, batch = read_manifest(landing, day)
    files = verify_files(landing, day, manifest)
    loaded_at = loaded_at or dt.datetime.now(dt.UTC).replace(tzinfo=None)
    counts: dict[str, int] = {}
    con.execute("BEGIN TRANSACTION")
    try:
        con.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
        for source, table, path, expected in files:
            name = lake_table(source, table)
            src = f"read_parquet({_sql_str(str(path))})"
            incoming = _columns(con, f"SELECT * FROM {src}")  # noqa: S608  identifiers only; values bound with ?
            existing = _table_columns(con, name)
            if existing is None:
                _create(con, name, src)
            else:
                body = [c for c in existing if c[0] not in AUDIT_COLUMNS]
                if body != incoming:
                    added = sorted(set(incoming) - set(body))
                    gone = sorted(set(body) - set(incoming))
                    raise LoadError(
                        f"{SCHEMA}.{name}: columns of {path.relative_to(landing)} differ from "
                        f"the table (new or changed: {added}; missing: {gone}); change the "
                        "table on purpose, the loader will not")
            cols = ", ".join(c for c, _ in incoming)
            con.execute(f"DELETE FROM {SCHEMA}.{name} WHERE _dt = ?", [day])  # noqa: S608  identifiers only; values bound with ?
            con.execute(
                f"INSERT INTO {SCHEMA}.{name} ({cols}, {', '.join(AUDIT_COLUMNS)}) "  # noqa: S608  identifiers only; values bound with ?
                f"SELECT {cols}, ?::DATE, ?, ?::TIMESTAMP, ? FROM {src}",
                [day, path.relative_to(landing).as_posix(), loaded_at, batch],
            )
            got = con.execute(f"SELECT count(*) FROM {SCHEMA}.{name} WHERE _dt = ?",  # noqa: S608  identifiers only; values bound with ?
                              [day]).fetchone()[0]
            if got != expected:
                raise LoadError(f"{SCHEMA}.{name}: {got} rows for {day}, manifest says {expected}")
            counts[f"{SCHEMA}.{name}"] = got
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    return counts
