---
id: de-0002
title: Name the DuckDB file dwh.duckdb, never after a schema
tags: [duckdb, catalog, schema, build-file, naming]
paths: [Makefile, dbt/profiles.yml]
status: active
created: 2026-11-22
last_verified: 2026-11-22
evidence:
  - docs/task-management/10-dbt-project.md::Build file renamed `dwh.duckdb`
  - Makefile::data/dev/dwh.duckdb
supersedes: []
---

## Rule

Every build file is `data/<target>/dwh.duckdb` (catalog `dwh`); no DuckDB file is named after
one of its schemas.

## Why

DuckDB names the catalog after the file. A file called `warehouse.duckdb` made
`warehouse.<table>` ambiguous between the catalog and the `warehouse` schema.

## How to apply

Keep the file name `dwh.duckdb` in the loader, the Makefile, `dbt/profiles.yml` and later
Airflow. Qualify tables as `<schema>.<table>`, or `dwh.<schema>.<table>` across attached files.

## Example

`make load` writes `data/dev/dwh.duckdb`; `make dbt-ci` builds `data/ci/dwh.duckdb`.
