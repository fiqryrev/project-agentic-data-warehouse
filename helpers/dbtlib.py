"""Static reading of the dbt project for the governance checkers (no database, no dbt run).

A model is read from its files only:
- `refs` and `sources` come from the `{{ ref(...) }}` and `{{ source(...) }}` calls in the SQL;
- the YAML entry comes from any `.yml` under `models/` that lists the model by name;
- `columns` are the names the final SELECT outputs. The Jinja is reduced to plain SQL (a ref
  becomes its model name, `dbt_audit_columns()` becomes its two columns, any other macro call
  becomes `null`) and DuckDB's own parser (`json_serialize_sql`) reads the select list, so
  DuckDB syntax such as `qualify`, lambdas and `filter` needs no second grammar.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import duckdb
import yaml

try:
    from helpers.govlib import REPO
except ModuleNotFoundError:
    from govlib import REPO  # type: ignore

DBT_DIR = REPO / "dbt"
LAYERS = ("staging", "warehouse", "mart")
AUDIT_SQL = "'0' as _dbt_invocation_id, current_timestamp as _dbt_updated_at"

_REF = re.compile(r"""ref\(\s*['"]([^'"]+)['"]\s*\)""")
_SOURCE = re.compile(r"""source\(\s*['"]([^'"]+)['"]\s*,\s*['"]([^'"]+)['"]\s*\)""")
_EXPR = re.compile(r"\{\{(.*?)\}\}", re.S)


@dataclass
class Model:
    name: str
    path: Path                      # relative to the dbt project
    sql: str
    layer: str | None               # first folder under models/
    domain: str | None              # second folder under models/
    refs: list[str] = field(default_factory=list)
    sources: list[tuple[str, str]] = field(default_factory=list)
    yml: dict | None = None
    yml_path: Path | None = None
    columns: list[str] | None = None    # None when the select list cannot be read
    parse_error: str | None = None


def render(sql: str) -> str:
    """The model's SQL with its Jinja reduced to something DuckDB can parse."""
    sql = re.sub(r"\{#.*?#\}", "", sql, flags=re.S)
    sql = re.sub(r"\{%.*?%\}", "", sql, flags=re.S)

    def one(m: re.Match) -> str:
        expr = m.group(1).strip()
        if r := _REF.fullmatch(expr):
            return r.group(1)
        if s := _SOURCE.fullmatch(expr):
            return f"{s.group(1)}.{s.group(2)}"
        if re.fullmatch(r"dbt_audit_columns\(\s*\)", expr):
            return AUDIT_SQL
        return "null"
    return _EXPR.sub(one, sql)


def _expr_name(expr: dict) -> str | None:
    if expr.get("alias"):
        return expr["alias"]
    if expr.get("class") == "COLUMN_REF":
        return expr["column_names"][-1]
    return None


def output_columns(sql: str) -> tuple[list[str] | None, str | None]:
    """(columns, error) of the final SELECT of a rendered query."""
    con = duckdb.connect()
    try:
        raw = con.execute("select json_serialize_sql(?)", [sql]).fetchone()[0]
    finally:
        con.close()
    tree = json.loads(raw)
    if tree.get("error"):
        return None, tree.get("error_message", "the SQL does not parse")
    node = tree["statements"][0]["node"]
    while node.get("type") == "SET_OPERATION_NODE":   # a union names its columns on the left
        node = node["left"]
    if node.get("type") != "SELECT_NODE":
        return None, f"the final statement is a {node.get('type')}, not a SELECT"
    cols = []
    for expr in node["select_list"]:
        if expr.get("class") == "STAR":
            return None, "the final SELECT uses *; list the columns"
        name = _expr_name(expr)
        if name is None:
            return None, "an output expression has no alias"
        cols.append(name)
    return cols, None


def _yml_models(models_dir: Path) -> dict[str, tuple[dict, Path]]:
    out: dict[str, tuple[dict, Path]] = {}
    for path in sorted(models_dir.rglob("*.yml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for entry in doc.get("models") or []:
            if isinstance(entry, dict) and entry.get("name"):
                out[entry["name"]] = (entry, path)
    return out


def load_sources(project: Path = DBT_DIR) -> dict[str, set[str]]:
    """{source name: {table names}} declared in the project's YAML."""
    out: dict[str, set[str]] = {}
    for path in sorted((project / "models").rglob("*.yml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for src in doc.get("sources") or []:
            out.setdefault(src["name"], set()).update(t["name"] for t in src.get("tables") or [])
    return out


def load_models(project: Path = DBT_DIR) -> list[Model]:
    models_dir = project / "models"
    ymls = _yml_models(models_dir)
    models = []
    for path in sorted(models_dir.rglob("*.sql")):
        rel = path.relative_to(models_dir)
        parts = rel.parts[:-1]
        sql = path.read_text(encoding="utf-8")
        exprs = [m.group(1).strip() for m in _EXPR.finditer(sql)]
        m = Model(
            name=path.stem, path=path.relative_to(project), sql=sql,
            layer=parts[0] if parts else None,
            domain=parts[1] if len(parts) > 1 else None,
            refs=[r.group(1) for e in exprs if (r := _REF.search(e))],
            sources=[(s.group(1), s.group(2)) for e in exprs if (s := _SOURCE.search(e))],
        )
        if m.name in ymls:
            m.yml, ypath = ymls[m.name]
            m.yml_path = ypath.relative_to(project)
        m.columns, m.parse_error = output_columns(render(sql))
        models.append(m)
    return models
