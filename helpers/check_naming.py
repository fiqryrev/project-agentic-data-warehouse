#!/usr/bin/env python3
"""check_naming: folders, table names and column names follow PLAN section 4.

Registry: .agents/rules/dbt-naming.yaml (layer folders, domains, cadences, class words).

Schemas: each layer's DuckDB schema has its folder's name: `+schema` in dbt_project.yml equals
the folder, and lake sources declare `schema: data_lake_layer` (issue 24).

Layout: every file under dbt/models/ is `<layer folder>/<table>/<table>.<sql|yml|md>`, one
folder per table, the folder named after the table. The lake folder holds no SQL (the loader
builds those tables); its YAML declares exactly the lake table its folder is named after.

Table names (one `__` between parts, each part snake_case):
- lake `<source>__<table>`, staging `staging__<source>__<table>`, source in source_domains;
- warehouse `dim__<domain>__<table>` or `fact__<domain>__<table>`;
- mart `rpt__<domain>__<table>__<cadence>`, cadence in cadences;
  domain in business_domains for warehouse and mart.

Column names of staging, warehouse and mart models (rules in .agents/rules/dbt.md):
- snake_case: lower case letters and digits, words joined by one `_`;
- a leading `_` only for the audit columns (AUDIT_COLUMNS);
- at least two words, the last one a class word (`order_id`, `paid_at`, `amount_idr`,
  `order_count`), or a flag that starts with `is_` or `has_`; a bare class word (`id`, `name`)
  says nothing about whose it is;
- a money column (a MONEY_WORDS word in the name) ends in its unit (`_idr`, `_usd`, `_pct`) unless its
  class word says it is not a measure (`refund_reason_code`, `spend_date`).
Lake columns keep the source system's names; staging renames them.
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
N = dbtlib.NAMING
SOURCE_DOMAINS = tuple(N["source_domains"])
BUSINESS_DOMAINS = tuple(N["business_domains"])
CADENCES = tuple(N["cadences"])
CLASS_WORDS = {w: kind for kind, words in N["class_words"].items() for w in words}
FLAG_PREFIXES = tuple(N["flag_prefixes"])
PREFIXES = {"lake": None, "staging": ("staging",), "warehouse": ("dim", "fact"), "mart": ("rpt",)}
PARTS = {"lake": 2, "staging": 3, "warehouse": 3, "mart": 4}
SHAPES = {"lake": "<source>__<table>", "staging": "staging__<source>__<table>",
          "warehouse": "dim__<domain>__<table> or fact__<domain>__<table>",
          "mart": "rpt__<domain>__<table>__<cadence>"}
FILE_TYPES = (".sql", ".yml", ".md")
AUDIT_COLUMNS = ("_dt", "_source_file", "_loaded_at", "_batch_id",
                 "_dbt_invocation_id", "_dbt_updated_at")
MONEY_WORDS = ("amount", "price", "fee", "cost", "spend", "budget", "payout", "commission",
               "revenue", "gross", "net", "tax", "discount")
UNIT_SUFFIXES = ("idr", "usd", "pct")
SNAKE = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$")


def layout_errors(project: Path) -> list[str]:
    """Every file sits at models/<layer folder>/<table>/<table>.<type>."""
    models = project / "models"
    errors = []
    for path in sorted(p for p in models.rglob("*") if p.is_file()):
        rel = path.relative_to(project)
        parts = path.relative_to(models).parts
        if path.name.startswith(".") or path.suffix not in FILE_TYPES:
            errors.append(f"{rel}: only .sql, .yml and .md files live under models/")
            continue
        if parts[0] not in dbtlib.LAYER_OF_FOLDER:
            errors.append(f"{rel}: '{parts[0]}' is not a layer folder "
                          f"({', '.join(dbtlib.LAYER_OF_FOLDER)})")
            continue
        if len(parts) != 3:
            errors.append(f"{rel}: a table sits in its own folder: "
                          f"models/{parts[0]}/<table>/<table>{path.suffix}")
            continue
        if path.stem != parts[1]:
            errors.append(f"{rel}: the file is named after its folder ({parts[1]}{path.suffix})")
        if parts[0] == dbtlib.LAKE_FOLDER and path.suffix == ".sql":
            errors.append(f"{rel}: the loader builds lake tables; the lake folder holds only "
                          f"the source .yml and .md")
    return errors


def name_errors(where: str, name: str, layer: str) -> list[str]:
    parts = name.split("__")
    if len(parts) != PARTS[layer] or not all(SNAKE.match(p) for p in parts):
        return [f"{where}: '{name}' is not {SHAPES[layer]} (snake_case parts joined by __)"]
    errors = []
    if PREFIXES[layer] and parts[0] not in PREFIXES[layer]:
        errors.append(f"{where}: '{name}' in {layer} must start with "
                      f"{' or '.join(p + '__' for p in PREFIXES[layer])}")
    domain = parts[0] if layer == "lake" else parts[1]
    allowed = SOURCE_DOMAINS if layer in ("lake", "staging") else BUSINESS_DOMAINS
    if domain not in allowed:
        kind = "source system" if layer in ("lake", "staging") else "business domain"
        errors.append(f"{where}: '{domain}' in '{name}' is not a {kind} ({', '.join(allowed)})")
    if layer == "mart" and parts[3] not in CADENCES:
        errors.append(f"{where}: cadence '{parts[3]}' is not one of {', '.join(CADENCES)}")
    return errors


def model_errors(m: dbtlib.Model) -> list[str]:
    if m.layer not in dbtlib.LAYERS:
        return []           # reported by layout_errors
    return name_errors(str(m.path), m.name, m.layer)


def schema_errors(project: Path) -> list[str]:
    errors = []
    for folder, schema in dbtlib.layer_schemas(project).items():
        if schema != folder:
            errors.append(f"dbt_project.yml: models in {folder}/ build into schema '{schema}'; "
                          f"the schema has the folder's name: +schema: {folder}")
    return errors


def lake_errors(project: Path) -> list[str]:
    errors = []
    for t in dbtlib.source_tables(project):
        where = str(t.yml_path)
        if t.source != "lake":
            errors.append(f"{where}: source '{t.source}'; the only source is 'lake'")
            continue
        if t.schema != dbtlib.LAKE_FOLDER:
            errors.append(f"{where}: lake table '{t.name}' is in schema '{t.schema}'; "
                          f"it lives in schema: {dbtlib.LAKE_FOLDER}")
        errors += name_errors(where, t.name, "lake")
        expected = Path("models") / dbtlib.LAKE_FOLDER / t.name / f"{t.name}.yml"
        if t.yml_path != expected:
            errors.append(f"{where}: lake table '{t.name}' is declared in {expected}")
    declared = {t.name for t in dbtlib.source_tables(project)}
    lake_dir = project / "models" / dbtlib.LAKE_FOLDER
    for folder in sorted(p for p in lake_dir.glob("*") if p.is_dir()):
        if folder.name not in declared:
            errors.append(f"models/{dbtlib.LAKE_FOLDER}/{folder.name}: declares no lake table "
                          f"'{folder.name}' in {folder.name}.yml")
    return errors


def column_errors(column: str) -> list[str]:
    if column.startswith("_"):
        return [] if column in AUDIT_COLUMNS else [
            f"'{column}': a leading _ is kept for the audit columns ({', '.join(AUDIT_COLUMNS)})"]
    if not SNAKE.match(column):
        return [f"'{column}': not snake_case (lower case, words joined by one _)"]
    words = column.split("_")
    if words[0] in FLAG_PREFIXES and len(words) > 1:
        return []
    if len(words) == 1:
        hint = f"order_{column}" if column in CLASS_WORDS else f"{column}_<class word>"
        return [f"'{column}': too generic; say whose or which and end in a class word "
                f"(for example {hint})"]
    if words[-1] not in CLASS_WORDS:
        return [f"'{column}': ends in '{words[-1]}', not a class word "
                f"({', '.join(CLASS_WORDS)}) or a flag ({', '.join(p + '_' for p in FLAG_PREFIXES)})"]
    if set(words) & set(MONEY_WORDS) and CLASS_WORDS[words[-1]] in ("measure", "money") \
            and words[-1] not in UNIT_SUFFIXES:
        return [f"'{column}': a money column ends in its unit ({', '.join('_' + u for u in UNIT_SUFFIXES)})"]
    return []


def check(models: list[dbtlib.Model], project: Path = dbtlib.DBT_DIR) -> list[str]:
    errors = layout_errors(project) + schema_errors(project) + lake_errors(project)
    for m in models:
        errors += model_errors(m)
        if m.layer not in dbtlib.LAYERS:
            continue
        yml_cols = [c.get("name", "") for c in (m.yml or {}).get("columns") or []]
        for col in dict.fromkeys((m.columns or []) + yml_cols):
            errors += [f"{m.path}: column {e}" for e in column_errors(col)]
    return errors


def main(argv: list[str] | None = None) -> int:
    project = Path(argv[0]) if argv else dbtlib.DBT_DIR
    return report(NAME, check(dbtlib.load_models(project), project))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
