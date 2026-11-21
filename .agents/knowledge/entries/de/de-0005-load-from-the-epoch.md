---
id: de-0005
title: The warehouse assumes the lake was loaded from the epoch
tags: [dbt, lake, backfill, epoch, airflow, catchup]
paths: [docs/task-management/10-dbt-project.md, Makefile]
status: active
created: 2026-11-22
last_verified: 2026-11-22
evidence:
  - docs/task-management/10-dbt-project.md::The warehouse assumes the lake was loaded from the epoch
  - "generator/DEFECTS.md::new seller: 120, then 1 a day"
supersedes: []
---

## Rule

Build the warehouse only on a lake loaded from 2026-01-01, the generator's epoch.

## Why

Sellers and campaigns are written once, on their creation day. A window that starts later has
order lines pointing at sellers it never loaded; a try from 2026-05-15 to 06-28 failed four
relationship tests.

## How to apply

Backfills start at 2026-01-01 (`make generate` and `make load` defaults, `make dbt-ci`).
Airflow's `warehouse_daily` uses `catchup=True` from the epoch (M7).

## Example

`make dbt-ci` loads 2026-01-01 to 01-03 before `dbt build --target ci`.
