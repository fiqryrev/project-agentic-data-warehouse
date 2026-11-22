#!/usr/bin/env python3
"""check_bundle: every table ships as a bundle of SQL, YAML, a doc and a key test.

For each model, in its table folder `models/<layer folder>/<table>/`:
- its YAML entry in `<table>.yml` and its doc block in `<table>.md`;
- the YAML description is `{{ doc("<table>") }}`, so the doc is the one description;
- every column the SQL outputs is listed in the YAML, every listed column is output by the SQL
  (read statically, see helpers/dbtlib.py), and every listed column has a description;
- a key test on the grain: one column with both `unique` and `not_null`, or a model-level
  `unique_combination` test.
A YAML entry with no SQL file fails too. Each lake table folder holds `<table>.yml` (the source
declaration, described by `doc()`) and `<table>.md` the same way.

The doc block (`<table>.md`) is exactly one `{% docs <table> %} ... {% enddocs %}` holding an
opening paragraph with no heading, then the H2 sections listed in doc_sections of
.agents/rules/dbt-naming.yaml, in that order, none empty; Change History is a table with at least
one row. No `{{` inside it: dbt would render it.
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

NAME = "check_bundle"
GRAIN_TESTS = ("unique_combination",)
DOC_SECTIONS = tuple(dbtlib.NAMING["doc_sections"])
_BLOCK = re.compile(r"\{%-?\s*docs\s+(\w+)\s*-?%\}(.*?)\{%-?\s*enddocs\s*-?%\}", re.S)


def doc_ref(name: str) -> re.Pattern:
    return re.compile(r"""\s*\{\{\s*doc\(\s*['"]%s['"]\s*\)\s*\}\}\s*""" % re.escape(name))


def doc_errors(text: str, name: str) -> list[str]:
    """Problems with the doc block of table `name`."""
    blocks = list(_BLOCK.finditer(text))
    if len(blocks) != 1:
        return [f"holds {len(blocks)} docs blocks; it holds exactly one: {{% docs {name} %}}"]
    block = blocks[0]
    errors = []
    if block.group(1) != name:
        errors.append(f"the docs block is named '{block.group(1)}', not '{name}'")
    if (text[:block.start()] + text[block.end():]).strip():
        errors.append("text outside the docs block")
    body = block.group(2)
    if "{{" in body:
        errors.append("'{{' inside the doc block; dbt renders it, write the name without braces")
    chunks = re.split(r"^## +(.+?) *$", body, flags=re.M)
    if not chunks[0].strip() or chunks[0].lstrip().startswith("#"):
        errors.append("no opening paragraph before the first section")
    sections = dict(zip(chunks[1::2], chunks[2::2]))
    found = [s for s in chunks[1::2] if s in DOC_SECTIONS]
    missing = [s for s in DOC_SECTIONS if s not in sections]
    if missing:
        errors.append(f"missing section(s): {', '.join('## ' + s for s in missing)}")
    elif found != list(DOC_SECTIONS):
        errors.append(f"sections out of order; the order is {', '.join(DOC_SECTIONS)}")
    for s in DOC_SECTIONS:
        if s in sections and not sections[s].strip():
            errors.append(f"section '## {s}' is empty")
    history = [ln for ln in sections.get("Change History", "").splitlines() if ln.strip().startswith("|")]
    if "Change History" in sections and len(history) < 3:
        errors.append("Change History has no row (a table: header, separator, one row per change)")
    return errors


def bundle_doc_errors(project: Path, where: str, name: str, doc_path: Path,
                      description) -> list[str]:
    errors = []
    if not doc_ref(name).fullmatch(str(description or "")):
        errors.append(f"{where}: the description is '{{{{ doc(\"{name}\") }}}}', the doc in {name}.md")
    path = project / doc_path
    if not path.is_file():
        errors.append(f"{where}: no doc; write {doc_path}")
    else:
        errors += [f"{doc_path}: {e}" for e in doc_errors(path.read_text(encoding="utf-8"), name)]
    return errors


def test_names(tests: list | None) -> set[str]:
    names = set()
    for t in tests or []:
        if isinstance(t, str):
            names.add(t)
        elif isinstance(t, dict) and t:
            names.add(next(iter(t)))
    return names


def _tests(node: dict) -> list:
    return (node.get("data_tests") or []) + (node.get("tests") or [])


def has_grain_test(yml: dict) -> bool:
    if test_names(_tests(yml)) & set(GRAIN_TESTS):
        return True
    return any({"unique", "not_null"} <= test_names(_tests(c)) for c in yml.get("columns") or [])


def model_errors(m: dbtlib.Model, project: Path = dbtlib.DBT_DIR) -> list[str]:
    where = str(m.path)
    if m.yml is None:
        return [f"{where}: no YAML entry; document it in {m.path.with_suffix('.yml')}"]
    errors = []
    if m.yml_path is not None and m.yml_path != m.path.with_suffix(".yml"):
        errors.append(f"{where}: its YAML is in {m.yml_path}; keep it in {m.path.with_suffix('.yml')}")
    errors += bundle_doc_errors(project, where, m.name, m.doc_path, m.yml.get("description"))
    yml_cols = [c for c in m.yml.get("columns") or [] if isinstance(c, dict)]
    names = [c.get("name") for c in yml_cols]
    for c in yml_cols:
        if not str(c.get("description") or "").strip():
            errors.append(f"{where}: column '{c.get('name')}' has no description")
    if m.columns is None:
        errors.append(f"{where}: cannot read the output columns ({m.parse_error})")
    else:
        for col in m.columns:
            if col not in names:
                errors.append(f"{where}: column '{col}' is output by the SQL but not in the YAML")
        for col in names:
            if col not in m.columns:
                errors.append(f"{where}: column '{col}' is in the YAML but the SQL does not output it")
    if not has_grain_test(m.yml):
        errors.append(f"{where}: no key test on the grain (a column with unique and not_null, "
                      f"or a model-level unique_combination)")
    return errors


def check(models: list[dbtlib.Model], project: Path = dbtlib.DBT_DIR) -> list[str]:
    errors = []
    for m in models:
        errors += model_errors(m, project)
    for s in dbtlib.source_tables(project):
        errors += bundle_doc_errors(project, str(s.yml_path), s.name, s.yml_path.with_suffix(".md"),
                                    s.yml.get("description"))
    sql_names = {m.name for m in models}
    for name, (_, ypath) in sorted(dbtlib._yml_models(project / "models").items()):
        if name not in sql_names:
            errors.append(f"{ypath.relative_to(project)}: YAML entry '{name}' has no SQL model")
    return errors


def main(argv: list[str] | None = None) -> int:
    project = Path(argv[0]) if argv else dbtlib.DBT_DIR
    return report(NAME, check(dbtlib.load_models(project), project))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
