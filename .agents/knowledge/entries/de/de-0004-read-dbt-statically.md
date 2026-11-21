---
id: de-0004
title: Governance checkers read dbt models statically with DuckDB's parser
tags: [governance, checkers, dbt, parser, ci, select-star]
paths: [helpers/dbtlib.py, .agents/rules/dbt.md]
status: active
created: 2026-11-22
last_verified: 2026-11-22
evidence:
  - docs/task-management/12-governance-checkers.md::Output columns come from DuckDB's own parser
  - helpers/dbtlib.py::json_serialize_sql
supersedes: []
---

## Rule

The model checkers (`check_naming`, `check_bundle`, `check_layers`, `check_audit_columns`) read
SQL and YAML files without running dbt or opening a database. Output columns come from
DuckDB's `json_serialize_sql` parse tree of the Jinja-reduced SQL.

## Why

They run in seconds in the governance job and need no build. DuckDB's own parser handles its
syntax (`qualify`, lambdas, `filter`) with no new dependency.

## How to apply

End every model with an explicit select list and alias every expression; a final `select *`
fails `check_bundle`, since its columns cannot be known statically. A new macro used in a
select list must be aliased (`{{ my_macro(x) }} as y`).

## Example

`uv run python -c "from helpers.dbtlib import load_models; print(load_models()[0].columns)"`
lists a model's output columns.
