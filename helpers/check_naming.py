#!/usr/bin/env python3
"""check_naming: model names, folders and column names follow PLAN section 4.

Model names (one `__` between parts, each part snake_case):
- `models/staging/<source>/staging__<source>__<table>`, source in SOURCE_DOMAINS;
- `models/warehouse/<domain>/dim__<domain>__<table>` or `fact__<domain>__<table>`;
- `models/mart/<domain>/rpt__<domain>__<table>__<cadence>`, cadence in CADENCES;
  domain in BUSINESS_DOMAINS for warehouse and mart.

Column names (rules in .agents/rules/dbt.md):
- snake_case: lower case letters and digits, words joined by one `_`;
- a leading `_` only for the audit columns (AUDIT_COLUMNS);
- no bare generic name (GENERIC_NAMES): say whose id, which date, what status;
- a money column (a MONEY_WORDS word in the name) ends in its unit (`_idr`, `_pct`) unless its
  last word says it is not a measure (`_id`, `_at`, `_date`, ...).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    from helpers import dbtlib
    from helpers.govlib import report
except ModuleNotFoundError:
    import dbtlib  # type: ignore
    from govlib import report  # type: ignore

NAME = "check_naming"
SOURCE_DOMAINS = ("shop", "ledger", "marketing", "gateway", "langfuse")
BUSINESS_DOMAINS = ("sales", "finance", "marketing", "ops")
CADENCES = ("daily", "weekly", "monthly", "quarterly", "yearly", "snapshot")
PREFIXES = {"staging": ("staging",), "warehouse": ("dim", "fact"), "mart": ("rpt",)}
PARTS = {"staging": 3, "warehouse": 3, "mart": 4}
AUDIT_COLUMNS = ("_dt", "_source_file", "_loaded_at", "_batch_id",
                 "_dbt_invocation_id", "_dbt_updated_at")
GENERIC_NAMES = ("id", "key", "name", "date", "time", "timestamp", "type", "status", "value",
                 "amount", "price", "code", "description")
MONEY_WORDS = ("amount", "price", "fee", "cost", "spend", "budget", "payout", "commission",
               "revenue", "gross", "net", "tax", "discount")
UNIT_SUFFIXES = ("idr", "pct")
NOT_A_MEASURE = ("id", "key", "at", "date", "name", "status", "reason", "type", "code",
                 "method", "flag")
SNAKE = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$")


def model_errors(m: dbtlib.Model) -> list[str]:
    where = str(m.path)
    if m.layer not in dbtlib.LAYERS:
        return [f"{where}: models live under models/{{{','.join(dbtlib.LAYERS)}}}/<domain>/"]
    if m.domain is None or len(m.path.parts) != 4:
        return [f"{where}: a model sits exactly one folder deep: models/{m.layer}/<domain>/"]
    allowed = SOURCE_DOMAINS if m.layer == "staging" else BUSINESS_DOMAINS
    errors = []
    if m.domain not in allowed:
        kind = "source system" if m.layer == "staging" else "business domain"
        errors.append(f"{where}: folder '{m.domain}' is not a {kind} ({', '.join(allowed)})")
    parts = m.name.split("__")
    shape = {"staging": "staging__<source>__<table>",
             "warehouse": "dim__<domain>__<table> or fact__<domain>__<table>",
             "mart": "rpt__<domain>__<table>__<cadence>"}[m.layer]
    if len(parts) != PARTS[m.layer] or not all(SNAKE.match(p) for p in parts):
        return errors + [f"{where}: '{m.name}' is not {shape} (snake_case parts joined by __)"]
    if parts[0] not in PREFIXES[m.layer]:
        errors.append(f"{where}: '{m.name}' in {m.layer} must start with "
                      f"{' or '.join(p + '__' for p in PREFIXES[m.layer])}")
    if parts[1] != m.domain:
        errors.append(f"{where}: domain '{parts[1]}' in the name does not match folder '{m.domain}'")
    if m.layer == "mart" and parts[3] not in CADENCES:
        errors.append(f"{where}: cadence '{parts[3]}' is not one of {', '.join(CADENCES)}")
    return errors


def column_errors(column: str) -> list[str]:
    if column.startswith("_"):
        return [] if column in AUDIT_COLUMNS else [
            f"'{column}': a leading _ is kept for the audit columns ({', '.join(AUDIT_COLUMNS)})"]
    if not SNAKE.match(column):
        return [f"'{column}': not snake_case (lower case, words joined by one _)"]
    if column in GENERIC_NAMES:
        return [f"'{column}': too generic; name what it belongs to (for example order_{column})"]
    words = column.split("_")
    if (set(words) & set(MONEY_WORDS) and words[-1] not in UNIT_SUFFIXES
            and words[-1] not in NOT_A_MEASURE):
        return [f"'{column}': a money column ends in its unit ({', '.join('_' + u for u in UNIT_SUFFIXES)})"]
    return []


def check(models: list[dbtlib.Model]) -> list[str]:
    errors = []
    for m in models:
        errors += model_errors(m)
        yml_cols = [c.get("name", "") for c in (m.yml or {}).get("columns") or []]
        for col in dict.fromkeys((m.columns or []) + yml_cols):
            errors += [f"{m.path}: column {e}" for e in column_errors(col)]
    return errors


def main(argv: list[str] | None = None) -> int:
    project = Path(argv[0]) if argv else dbtlib.DBT_DIR
    return report(NAME, check(dbtlib.load_models(project)))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
