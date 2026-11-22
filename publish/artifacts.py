"""Where a daily run keeps its files: data/artifacts/<ds>/ (PLAN section 7)."""
from __future__ import annotations

import json
from pathlib import Path

ARTIFACTS = Path("data/artifacts")
LAYER_SCHEMAS = ("lake", "staging", "warehouse", "mart")


def day_dir(ds: str, root: Path = ARTIFACTS) -> Path:
    return root / ds


def read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def write_json(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")


OK_STATUSES = ("pass", "success", "warn")


def failed_nodes(run_results: dict | None) -> list[str]:
    """Every dbt node (model or test) that errored, failed or was skipped."""
    return [f"{r.get('unique_id')} ({r.get('status')})" for r in (run_results or {}).get("results") or []
            if str(r.get("status", "")).lower() not in OK_STATUSES]


def dbt_test_counts(run_results: dict | None) -> dict[str, int]:
    """dbt test results by outcome: pass, warn, fail (fail also counts error and skipped)."""
    counts = {"pass": 0, "warn": 0, "fail": 0}
    for r in (run_results or {}).get("results") or []:
        if not str(r.get("unique_id", "")).startswith("test."):
            continue
        status = str(r.get("status", "")).lower()
        if status in ("pass", "success"):
            counts["pass"] += 1
        elif status == "warn":
            counts["warn"] += 1
        else:
            counts["fail"] += 1
    return counts
