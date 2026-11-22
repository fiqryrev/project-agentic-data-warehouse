#!/usr/bin/env python3
"""check_golden: every golden question in evals/golden/ can be asked and scored (PLAN 8.3).

- Fields: `id` (`g-NNNN`, unique, the file name starts with it), `question`, `reference_sql`,
  `kind` (`scalar` or `rows`, and `rows` names its `key` column), `tolerance_pct` (0 to 100),
  `needs_day` (a date); no other field.
- The reference SQL is one read-only `select` or `with` statement that reads only
  `data_warehouse_layer` and `data_mart_layer` models that exist in the dbt project (the snapshot
  holds nothing else).
- A string literal other than `date '...'` or `timestamp '...'` needs `evidence`: `da-` entries
  that verify it (rule: verify a literal before filtering on it).
"""
from __future__ import annotations

import datetime as dtm
import re
import sys
from pathlib import Path

import yaml

try:
    from helpers.govlib import REPO, report
except ModuleNotFoundError:
    from govlib import REPO, report  # type: ignore

NAME = "check_golden"
GOLDEN = Path("evals/golden")
FIELDS = {"id", "question", "reference_sql", "kind", "key", "tolerance_pct", "needs_day", "evidence"}
REQUIRED = {"id", "question", "reference_sql", "kind", "needs_day"}
SERVED = ("data_warehouse_layer", "data_mart_layer")
WRITE_WORDS = re.compile(r"\b(insert|update|delete|merge|create|drop|alter|attach|detach|copy|"
                         r"pragma|install|load|export|import|set|call|checkpoint)\b", re.I)
TABLE_REF = re.compile(r"\b(?:analytics\.)?([a-z_]+_layer|[a-z_]+)\.([a-z0-9_]+)\b", re.I)
LITERAL = re.compile(r"(\b(?:date|timestamp)\s*)?'((?:[^']|'')*)'", re.I)


def layer_models(repo: Path) -> dict[str, set[str]]:
    root = repo / "dbt" / "models"
    return {s: {p.name for p in (root / s).iterdir() if p.is_dir()} if (root / s).is_dir() else set()
            for s in SERVED}


def da_entries(repo: Path) -> set[str]:
    d = repo / ".agents" / "knowledge" / "entries" / "da"
    return {"-".join(p.stem.split("-")[:2]) for p in d.glob("da-*.md")} if d.is_dir() else set()


def strip_sql_strings(sql: str) -> str:
    return LITERAL.sub("''", re.sub(r"--[^\n]*", "", sql))


def check_question(path: Path, doc, models: dict[str, set[str]], entries: set[str]) -> list[str]:
    where = path.as_posix()
    if not isinstance(doc, dict):
        return [f"{where}: not a mapping"]
    errors = [f"{where}: missing field {f}" for f in sorted(REQUIRED - set(doc))]
    errors += [f"{where}: unknown field {f}" for f in sorted(set(doc) - FIELDS)]
    qid = str(doc.get("id", ""))
    if not re.fullmatch(r"g-\d{4}", qid):
        errors.append(f"{where}: id {qid!r} is not g-NNNN")
    elif not path.name.startswith(qid + "-"):
        errors.append(f"{where}: file name does not start with {qid}-")
    if not str(doc.get("question", "")).strip():
        errors.append(f"{where}: empty question")
    kind = doc.get("kind")
    if kind not in ("scalar", "rows"):
        errors.append(f"{where}: kind {kind!r} is not scalar or rows")
    sql = str(doc.get("reference_sql", ""))
    if kind == "rows" and (not doc.get("key") or not re.search(rf"\b{re.escape(str(doc['key']))}\b", sql)):
        errors.append(f"{where}: kind rows needs a key column that the reference SQL selects")
    tol = doc.get("tolerance_pct", 0)
    if not isinstance(tol, (int, float)) or isinstance(tol, bool) or not 0 <= tol <= 100:
        errors.append(f"{where}: tolerance_pct {tol!r} is not a number from 0 to 100")
    day = doc.get("needs_day")
    if day is not None and not isinstance(day, dtm.date):
        try:
            dtm.date.fromisoformat(str(day))
        except ValueError:
            errors.append(f"{where}: needs_day {day!r} is not a date")
    errors += check_sql(where, sql, models)
    literals = [m.group(2) for m in LITERAL.finditer(sql) if not m.group(1)]
    evidence = doc.get("evidence") or []
    if literals and not evidence:
        errors.append(f"{where}: literal(s) {literals} need evidence (a da- entry that verifies them)")
    for e in evidence:
        if e not in entries:
            errors.append(f"{where}: evidence {e} is not a da- entry")
    return errors


def check_sql(where: str, sql: str, models: dict[str, set[str]]) -> list[str]:
    bare = strip_sql_strings(sql).strip()
    if not re.match(r"(select|with)\b", bare, re.I):
        return [f"{where}: reference_sql must start with select or with"]
    errors = []
    if ";" in bare.rstrip().rstrip(";"):
        errors.append(f"{where}: reference_sql holds more than one statement")
    if (m := WRITE_WORDS.search(bare)):
        errors.append(f"{where}: reference_sql uses {m.group(1).lower()!r}; only reads are allowed")
    refs = [(s.lower(), t.lower()) for s, t in TABLE_REF.findall(bare) if s.lower().endswith("_layer")]
    if not refs:
        errors.append(f"{where}: reference_sql reads no data_warehouse_layer or data_mart_layer model")
    for schema, table in refs:
        if schema not in SERVED:
            errors.append(f"{where}: {schema}.{table} is not served (only {', '.join(SERVED)})")
        elif table not in models[schema]:
            errors.append(f"{where}: {schema}.{table} is not a dbt model")
    return errors


def check(repo: Path = REPO) -> list[str]:
    folder = repo / GOLDEN
    files = sorted(folder.glob("g-*.yaml"))
    if not files:
        return [f"{GOLDEN}: no golden question"]
    models, entries = layer_models(repo), da_entries(repo)
    errors, seen = [], {}
    for path in files:
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as e:
            errors.append(f"{path.relative_to(repo)}: invalid YAML ({e})")
            continue
        errors += check_question(path.relative_to(repo), doc, models, entries)
        if isinstance(doc, dict) and doc.get("id"):
            if doc["id"] in seen:
                errors.append(f"{path.relative_to(repo)}: id {doc['id']} also in {seen[doc['id']]}")
            seen[doc["id"]] = path.name
    return errors


def main() -> int:
    return report(NAME, check())


if __name__ == "__main__":
    sys.exit(main())
