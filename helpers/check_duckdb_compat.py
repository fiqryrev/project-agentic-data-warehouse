#!/usr/bin/env python3
"""check_duckdb_compat: the loader, dbt's DuckDB and Auto Ontology's DuckDB open one file.

1. The loader's DuckDB spec in pyproject.toml equals `loader` in infra/duckdb-pins.yaml.
2. One generated day is loaded into a fresh file with the loader's own DuckDB.
3. Each reader version in the pins file opens that file in an isolated environment
   (`uv run --isolated --no-project --with duckdb==<version>`): it must see the same lake
   tables, row counts and the audit-column comment. A `rw` reader (dbt) also writes a table,
   which the loader's build must read back.

The real dbt binary joins this check in M4, when `dbt build --target ci` runs in CI.
Needs network the first time, to fetch the reader wheels.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import tomllib
from collections.abc import Callable
from pathlib import Path

import duckdb
import yaml

try:
    from helpers.govlib import REPO, report
except ModuleNotFoundError:
    from govlib import REPO, report  # type: ignore

NAME = "check_duckdb_compat"
PINS = REPO / "infra" / "duckdb-pins.yaml"
PROBE_DATE = "2026-01-02"

# Runs inside the reader environment; prints what it sees as JSON.
PROBE = r"""
import json, sys, duckdb
path, mode = sys.argv[1], sys.argv[2]
con = duckdb.connect(path, read_only=(mode == "ro"))
tables = con.execute(
    "SELECT table_name FROM information_schema.tables WHERE table_schema = 'lake' ORDER BY 1"
).fetchall()
rows = {t: con.execute(f"SELECT count(*) FROM lake.{t}").fetchone()[0] for (t,) in tables}
comment = con.execute(
    "SELECT comment FROM duckdb_columns() WHERE schema_name = 'lake' "
    "AND table_name = 'shop__orders' AND column_name = '_dt'"
).fetchone()
if mode == "rw":
    con.execute("CREATE OR REPLACE TABLE main.compat_probe AS SELECT 42 AS answer")
con.close()
print(json.dumps({"version": duckdb.__version__, "rows": rows,
                  "comment": comment[0] if comment else None}))
"""

Runner = Callable[[str, str, str], dict]


def uv_runner(version: str, db: str, mode: str) -> dict:
    out = subprocess.run(
        ["uv", "run", "--isolated", "--no-project", "--quiet", "--with", f"duckdb=={version}",
         "python", "-c", PROBE, db, mode],
        check=True, capture_output=True, text=True,
    ).stdout
    return json.loads(out.strip().splitlines()[-1])


def load_pins(path: Path = PINS) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def pyproject_duckdb_spec(path: Path = REPO / "pyproject.toml") -> str | None:
    deps = tomllib.loads(path.read_text(encoding="utf-8"))["project"]["dependencies"]
    for dep in deps:
        m = re.match(r"^duckdb\s*(.*)$", dep)
        if m:
            return m.group(1).replace(" ", "")
    return None


def build_probe_file(db: Path) -> dict:
    """Generate one day and load it with the loader's DuckDB; return what that build sees."""
    import datetime as dtm

    from generator.write import write_day
    from loader.load import load_day

    landing = db.parent / "landing"
    day = dtm.date.fromisoformat(PROBE_DATE)
    write_day(42, day, landing)
    con = duckdb.connect(str(db))
    rows = {k.split(".", 1)[1]: v for k, v in load_day(con, landing, day).items()}
    comment = con.execute(
        "SELECT comment FROM duckdb_columns() WHERE schema_name = 'lake' "
        "AND table_name = 'shop__orders' AND column_name = '_dt'").fetchone()[0]
    con.close()
    return {"version": duckdb.__version__, "rows": dict(sorted(rows.items())), "comment": comment}


def check(pins: dict, runner: Runner = uv_runner, workdir: Path | None = None,
          loader_spec: str | None = None) -> list[str]:
    errors = []
    spec = loader_spec if loader_spec is not None else pyproject_duckdb_spec()
    if spec != str(pins.get("loader", "")).replace(" ", ""):
        errors.append(f"pyproject.toml pins duckdb{spec}, infra/duckdb-pins.yaml says "
                      f"{pins.get('loader')}; keep them equal")
    readers = pins.get("readers") or {}
    if not readers:
        return errors + ["infra/duckdb-pins.yaml lists no readers"]
    with tempfile.TemporaryDirectory(dir=workdir) as tmp:
        db = Path(tmp) / "compat.duckdb"
        expected = build_probe_file(db)
        for name, r in sorted(readers.items()):
            version, mode = str(r.get("version")), r.get("mode", "ro")
            if mode not in ("ro", "rw"):
                errors.append(f"{name}: mode must be ro or rw")
                continue
            try:
                seen = runner(version, str(db), mode)
            except Exception as exc:  # noqa: BLE001 - report every failure the same way
                errors.append(f"{name}: DuckDB {version} could not open the file ({exc})")
                continue
            if seen.get("version") != version:
                errors.append(f"{name}: expected DuckDB {version}, the probe ran {seen.get('version')}")
            if seen.get("rows") != expected["rows"]:
                errors.append(f"{name}: DuckDB {version} sees different lake row counts")
            if seen.get("comment") != expected["comment"]:
                errors.append(f"{name}: DuckDB {version} does not read the column comments")
            if mode == "rw":
                con = duckdb.connect(str(db), read_only=True)
                try:
                    answer = con.execute("SELECT answer FROM main.compat_probe").fetchone()[0]
                except duckdb.Error as exc:
                    answer = f"error: {exc}"
                con.close()
                if answer != 42:
                    errors.append(f"{name}: the loader's DuckDB cannot read what {version} wrote ({answer})")
            print(f"[{NAME}] {name}: DuckDB {seen.get('version')} ({mode}) read "
                  f"{sum((seen.get('rows') or {}).values()):,} lake rows")
    return errors


def main() -> int:
    return report(NAME, check(load_pins()))


if __name__ == "__main__":
    sys.exit(main())
