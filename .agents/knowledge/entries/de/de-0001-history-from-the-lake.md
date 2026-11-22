---
id: de-0001
title: Build dimension history from the lake, not from dbt snapshots
tags: [dbt, scd2, history, dimensions, backfill, snapshots]
paths: [dbt/models/warehouse/sales/dim__sales__customers.sql, dbt/models/warehouse/sales/dim__sales__products.sql]
status: active
created: 2026-11-22
last_verified: 2026-11-22
evidence:
  - docs/task-management/10-dbt-project.md::History from the lake, not from dbt snapshots
  - dbt/models/warehouse/sales/dim__sales__customers.sql::Built from the lake's history
supersedes: []
---

## Rule

Slowly changing dimensions (`valid_from`, `valid_to`, `is_current`) are computed with window
functions over every version the lake holds, not with dbt snapshots.

## Why

A snapshot records build time, so rebuilding after a backfill gives a different history than
the first run. The lake is append-only by `_dt` and keeps every version the source wrote, so a
full rebuild reproduces the same history every time.

## How to apply

Make the source write a new row on each change (with `updated_at`), keep all of them in staging,
and derive `valid_from = updated_at`, `valid_to = lead(updated_at)`, `is_current = valid_to is
null`. Test with `scd2_valid` (no overlap, one current row per key).

## Example

`dim__sales__customers`: one row per customer version; `fact__sales__order_items` joins the
version valid at the order's timestamp.
