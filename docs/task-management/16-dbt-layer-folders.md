# 16: dbt layout: four layer folders, one folder per table with sql, yml and md

## Goal

The owner asked for a dbt layout where a table is one folder holding its SQL, YAML and doc,
under four layer folders, with the naming convention enforced. Done when `make checks` and
`make dbt-ci` are green with the same dbt test results, and each new rule has a bad-model test.

## Plan (as approved)

Approved in chat on 2026-11-22.

1. Move every model to `dbt/models/data_<layer>_layer/<table>/<table>.{sql,yml}`; split the
   per-domain YAML files and `_sources.yml` (one lake folder per lake table, no SQL there).
2. Write `<table>.md` for every table, lake included: one `{% docs %}` block with an opening
   paragraph and seven sections in order; the YAML description becomes `doc()`.
3. Naming: folder = table = file names; the domain is read from the name; model columns end in
   a class word from a registry, staging renames lake columns.
4. Update `dbtlib`, `check_naming`, `check_bundle`, `check_layers`, the fixture project and the
   tests, the knowledge entries' paths, PLAN sections 4 and 10, AGENTS.md and the dbt rules.
5. M7 (Airflow) follows in its own issue.

## Decisions

- **Lake folders hold the source YAML and doc only.** The loader builds lake tables, so a SQL
  file there would be a lie. dbt accepts the `lake` source declared across 15 files, one table
  each (`dbt build` result unchanged).
- **One registry file, `.agents/rules/dbt-naming.yaml`.** Layer folders, source systems,
  business domains, cadences, class words, flag prefixes and doc sections live in one YAML the
  checkers read, so adding a domain or a class word is a one-line change with no code edit.
- **Class words.** `id`, `key`, `code`, `number`, `name`, `address`, `description`, `status`,
  `type`, `at`, `date`, `idr`, `pct`, `count`, `quantity`; flags start `is_` or `has_`. A
  one-word column fails (it is a bare class word, or says nothing about whose it is). Lake
  columns are not checked: they are the source's names, and staging renames them.
- **Renames** (staging aliases the lake name; warehouse, mart, tests and macros follow):
  `email` -> `email_address`, `city` -> `city_name`, `province` -> `province_name`,
  `channel` -> `channel_name`, `courier` -> `courier_name`, `payment_method` ->
  `payment_method_code`, `refund_reason` -> `refund_reason_code`, `line_no` -> `line_number`,
  `quantity` -> `item_quantity`, `impressions` -> `impression_count`, `clicks` ->
  `click_count`; voucher `valid_from`/`valid_to` (dates) -> `valid_from_date`/`valid_to_date`;
  history `valid_from`/`valid_to` (timestamps) -> `valid_from_at`/`valid_to_at`; mart
  `orders`, `cancelled_orders`, `delivered_orders`, `units`, `invoices` -> `order_count`,
  `cancelled_order_count`, `delivered_order_count`, `unit_count`, `invoice_count`.
- **The doc is the description.** The YAML description must be exactly `{{ doc("<table>") }}`,
  so `persist_docs` writes the whole doc into the table comment Auto Ontology reads, and there
  is no second description to drift. Extra H2 sections are allowed between the seven; `{{`
  inside a doc fails because dbt renders doc blocks as Jinja.
- **Docs were drafted by two subagents** (lake and staging; warehouse and mart) from one brief,
  then checked by `check_bundle` and read over before commit.

## Done

- `uv run pytest -q` -> 239 passed (governance tests rewritten for the new layout: naming 46,
  bundle 31 including ten bad doc blocks, layers and audit columns on the new paths).
- `make checks` -> all eleven checkers OK; `check_naming`, `check_bundle` and `check_layers` read
  the 46 table folders (15 lake, 15 staging, 13 warehouse, 3 mart).
- `make dbt-ci` -> `Summary: 115 total | 110 success | 5 warn`, the same as before the move.
- The doc reaches DuckDB: the comment on `mart.rpt__finance__revenue__daily` starts with the
  doc's opening paragraph (`select comment from duckdb_tables() where table_name = ...`).
- Fixed in passing: `staging__shop__vouchers.valid_to_date` said "null while it is current";
  the generator always sets it to the month end (`generator/model.py`, `voucher`).

## Open

- Column types (`_at` timestamp, `_date` date, `is_` boolean) are still not checked.
- A `meta.version` in the YAML could be tied to the Change History's latest row; not needed yet.
- M7 (Airflow compose, `warehouse_daily`, `ops.run_log`, backfill) in its own issue.
