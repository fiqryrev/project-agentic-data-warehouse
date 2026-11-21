---
id: de-0003
title: Load a lake day in one transaction with a deterministic batch id
tags: [loader, lake, transaction, idempotent, batch, audit-columns]
paths: [loader/load.py, docs/task-management/8-lake-loader.md]
status: active
created: 2026-11-22
last_verified: 2026-11-22
evidence:
  - docs/task-management/8-lake-loader.md::The whole day is one transaction
  - loader/load.py::A day loads in one transaction
  - loader/load.py::<date>-<first 12 hex of the manifest SHA-256>
supersedes: []
---

## Rule

A partition date loads in one transaction: for each table, delete that `_dt`, insert the new
rows. `_batch_id` is `<date>-<first 12 hex of the manifest SHA-256>`.

## Why

If any table fails (checksum, schema drift), no table of that day changes, so the lake is never
half-loaded. Same input gives the same batch id, so loading a day twice leaves counts unchanged
and a reload is visible only in `_loaded_at`.

## How to apply

Reload a day by rerunning the loader for that date; never patch lake rows by hand. Compare
`_batch_id` to tell whether two loads read the same files.

## Example

`uv run python -m loader --date 2026-01-02` twice: the same row counts and `_batch_id`, a
newer `_loaded_at`.
