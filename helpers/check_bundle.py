#!/usr/bin/env python3
"""check_bundle: every model ships as a bundle of SQL, YAML, docs and a key test.

For each model under dbt/models/:
- a YAML entry in a `.yml` file in the same folder;
- a non-empty model description;
- every column the SQL outputs is listed in the YAML, every listed column is output by the SQL
  (read statically, see helpers/dbtlib.py), and every listed column has a description;
- a key test on the grain: one column with both `unique` and `not_null`, or a model-level
  `unique_combination` test.
A YAML entry with no SQL file fails too.
"""
from __future__ import annotations

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


def model_errors(m: dbtlib.Model) -> list[str]:
    where = str(m.path)
    if m.yml is None:
        return [f"{where}: no YAML entry; document it in a .yml next to the SQL"]
    errors = []
    if m.yml_path is not None and m.yml_path.parent != m.path.parent:
        errors.append(f"{where}: its YAML is in {m.yml_path}; keep it in the model's folder")
    if not str(m.yml.get("description") or "").strip():
        errors.append(f"{where}: no model description")
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
        errors += model_errors(m)
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
