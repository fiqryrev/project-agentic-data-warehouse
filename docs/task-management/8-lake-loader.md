# 8: M3 lake loader with audit columns

## Goal

PLAN section 11, row M3 (load step in section 6, audit columns in section 7): load landing
partitions into `lake` with audit columns, plus `check_duckdb_compat`. Done when loading a
day twice leaves counts unchanged.

## Plan (as approved)

`loader/` with DuckDB `>=1.5.5,<1.6`; one table per source table, `lake.<source>__<table>`,
with `_dt`, `_source_file`, `_loaded_at`, `_batch_id`; per date, delete then insert in one
transaction; verify manifest checksums before loading and row counts after; stop on schema
drift. `infra/duckdb-pins.yaml` and `check_duckdb_compat` (loader writes, DuckDB 1.5.4 and
1.5.5 open the file in isolated environments). Tests, a small Makefile, docs, worknote.

## Decisions

- **The whole day is one transaction**, not one per table: if any table fails (checksum,
  drift, count), nothing from that date is written, and the earlier state stays (tested,
  including tables created in the same transaction).
- **Manifest required.** Every partition must come with the generator's manifest; checksums
  are verified before the first write, row counts after each insert. Platform sources (M8,
  M11) will write the same manifest shape.
- **`_batch_id` = `<date>-<first 12 hex of the manifest SHA-256>`**, so the same input gives
  the same batch id and a changed partition gets a new one. `_loaded_at` is the only value
  that changes between reloads.
- **`_source_file` is relative to the landing folder** (no home paths in the data).
- **Schema drift stops the load** with the columns that differ; the loader never alters a
  table on its own. Changing a lake table is a deliberate change in its own PR.
- **Comments on lake tables and audit columns** are written at creation, so the compat check
  can confirm that other DuckDB builds read comments (Auto Ontology reads them from the
  serving file later).
- **`check_duckdb_compat` uses Python DuckDB builds** of the versions dbt and Auto Ontology
  use (1.5.4 read-write, 1.5.5 read-only), installed by `uv run --isolated --with`. The real
  dbt binary joins in M4 with `dbt build --target ci`. Pins live in `infra/duckdb-pins.yaml`
  and must match `pyproject.toml` (checked).
- **Manual loads write `data/dev/warehouse.duckdb`** (CLI and `make load` default), not the daily
  build file (Codex review on PR #9): only Airflow writes `data/build/`, and it will pass `--db`
  explicitly in M7. `data/` stays gitignored.
- **Branch in the session's own worktree**, as in M2.

## Done

- `uv run python -m loader --start 2026-01-01 --end 2026-01-03` then `--date 2026-01-02` again:
  `lake.shop__orders` keeps 475 / 886 / 1,170 rows for the three dates; 15 lake tables.
- `uv run python -m helpers.check_duckdb_compat` → OK: DuckDB 1.5.5 (ro) and 1.5.4 (rw) read
  4,439 lake rows from a file written by 1.5.6, and 1.5.6 reads back what 1.5.4 wrote.
- `uv run pytest -q` → 93 passed, including `tests/loader/test_loader.py` (loading a day twice
  leaves counts unchanged, audit columns, same batch id for the same input, reload touches only
  its date, late rows keep the partition date, checksum and drift failures roll back) and
  `tests/governance/test_check_duckdb_compat.py`.

## Open

- M4 builds staging from these tables (dedupe, latest row per order, casing, renamed status).
- M7 wires `generate_source` and `load_lake` into the Airflow DAG.
