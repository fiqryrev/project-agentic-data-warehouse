"""Static reading of the dbt project for the governance checkers (no database, no dbt run).

A model is read from its files only:
- `refs` and `sources` come from the `{{ ref(...) }}` and `{{ source(...) }}` calls in the SQL;
- the YAML entry comes from any `.yml` under `models/` that lists the model by name;
- `columns` are the names the final SELECT outputs. The Jinja is reduced to plain SQL (a ref
  becomes its model name, `dbt_audit_columns()` becomes its two columns, `config()` disappears,
  any other macro call becomes `null`) and DuckDB's own parser (`json_serialize_sql`) reads the
  select list, so DuckDB syntax such as `qualify`, lambdas and `filter` needs no second grammar.
  Each `{% if %}`/`{% elif %}`/`{% else %}` combination is rendered and parsed on its own, and
  all of them must output the same columns; a `{% for %}` loop cannot be read and fails.
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


class JinjaError(ValueError):
    """Jinja the checkers cannot reduce to plain SQL."""


MAX_VARIANTS = 64
_TAG = re.compile(r"\{%-?\s*(\w+)(.*?)-?%\}", re.S)


def _expressions(sql: str) -> str:
    def one(m: re.Match) -> str:
        expr = m.group(1).strip()
        if r := _REF.fullmatch(expr):
            return r.group(1)
        if s := _SOURCE.fullmatch(expr):
            return f"{s.group(1)}.{s.group(2)}"
        if re.fullmatch(r"dbt_audit_columns\(\s*\)", expr):
            return AUDIT_SQL
        if re.fullmatch(r"config\(.*\)", expr, re.S):
            return ""
        if expr == "this":
            return "this"
        return "null"
    return _EXPR.sub(one, sql)


def _variants(sql: str) -> list[str]:
    """Every text an if/elif/else structure can produce (tags other than if and for dropped).

    A `{% for %}` loop raises JinjaError: its output cannot be known without running it.
    """
    pos, stack = 0, [[[""]]]          # stack of if-blocks; each: list of branches of variants
    def add(text: str) -> None:
        branch = stack[-1][-1]
        branch[:] = [v + text for v in branch]
    def close_block(block: list[list[str]], has_else: bool) -> list[str]:
        out = [v for branch in block for v in branch]
        return out + ([""] if not has_else else [])
    else_seen = [False]
    for m in _TAG.finditer(sql):
        add(sql[pos:m.start()])
        pos = m.end()
        tag = m.group(1)
        if tag == "for":
            raise JinjaError("a {% for %} loop cannot be read statically")
        if tag == "if":
            stack.append([[""]])
            else_seen.append(False)
        elif tag in ("elif", "else"):
            if len(stack) == 1:
                raise JinjaError(f"{{% {tag} %}} without {{% if %}}")
            stack[-1].append([""])
            else_seen[-1] = else_seen[-1] or tag == "else"
        elif tag == "endif":
            if len(stack) == 1:
                raise JinjaError("{% endif %} without {% if %}")
            block, has_else = stack.pop(), else_seen.pop()
            options = close_block(block, has_else)
            branch = stack[-1][-1]
            branch[:] = [v + o for v in branch for o in options]
            if len(branch) > MAX_VARIANTS:
                raise JinjaError(f"more than {MAX_VARIANTS} if/else combinations")
    if len(stack) != 1:
        raise JinjaError("{% if %} without {% endif %}")
    add(sql[pos:])
    return list(dict.fromkeys(stack[0][0]))


def render_all(sql: str) -> list[str]:
    """Every plain-SQL text the model can render to, one per if/else combination."""
    sql = re.sub(r"\{#.*?#\}", "", sql, flags=re.S)
    return [_expressions(v) for v in _variants(sql)]


def render(sql: str) -> str:
    """The model's SQL with its Jinja reduced to something DuckDB can parse (first variant)."""
    return render_all(sql)[0]


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
    if len(tree["statements"]) != 1:
        return None, f"the model renders to {len(tree['statements'])} statements, not one SELECT"
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


def model_columns(sql: str) -> tuple[list[str] | None, str | None]:
    """(columns, error): every if/else variant must parse to one SELECT with the same columns."""
    try:
        variants = render_all(sql)
    except JinjaError as exc:
        return None, str(exc)
    seen: list[str] | None = None
    for i, text in enumerate(variants, 1):
        cols, err = output_columns(text)
        if err:
            where = f" (if/else variant {i} of {len(variants)})" if len(variants) > 1 else ""
            return None, err + where
        if seen is not None and cols != seen:
            return None, (f"if/else branches output different columns: {seen} and {cols}; "
                          f"keep one select list and branch inside expressions or WHERE")
        seen = cols
    return seen, None


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
        m.columns, m.parse_error = model_columns(sql)
        models.append(m)
    return models
