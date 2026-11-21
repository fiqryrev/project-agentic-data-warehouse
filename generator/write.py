"""Write one day's tables as Parquet, plus a manifest with row counts and checksums.

Layout under the output folder (default `data/landing/`, gitignored):
    <source>/<table>/dt=YYYY-MM-DD/part-0.parquet
    _manifest/dt=YYYY-MM-DD/manifest.json
Every table gets a file every day, empty when nothing happened, so a loader can replace a
partition without asking whether it exists. Writer settings are fixed and nothing time-based
goes into the file, so the same input gives the same bytes.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from generator import config as c
from generator.model import build_day
from generator.schemas import SCHEMAS


def partition_path(out: Path, source: str, table: str, day: dt.date) -> Path:
    return out / source / table / f"dt={day.isoformat()}" / "part-0.parquet"


def manifest_path(out: Path, day: dt.date) -> Path:
    return out / "_manifest" / f"dt={day.isoformat()}" / "manifest.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_day(seed: int, day: dt.date, out: Path) -> dict:
    tables = build_day(seed, day)
    missing = set(SCHEMAS) ^ set(tables)
    if missing:
        raise RuntimeError(f"tables and schemas disagree: {sorted(missing)}")
    manifest = {"generator_version": c.GENERATOR_VERSION, "seed": seed,
                "date": day.isoformat(), "tables": {}}
    for (source, table), schema in sorted(SCHEMAS.items()):
        path = partition_path(out, source, table, day)
        path.parent.mkdir(parents=True, exist_ok=True)
        arrow = pa.Table.from_pylist(tables[source, table], schema=schema)
        pq.write_table(arrow, path, compression="snappy", use_dictionary=True,
                       write_statistics=True, row_group_size=1_000_000)
        manifest["tables"][f"{source}.{table}"] = {"rows": arrow.num_rows, "sha256": sha256(path)}
    mpath = manifest_path(out, day)
    mpath.parent.mkdir(parents=True, exist_ok=True)
    mpath.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest
