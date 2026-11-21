# 10: M4 dbt project (staging, warehouse, mart)

## Goal

PLAN section 11, row M4 (layers and naming in section 4, audit columns and history in
section 7): staging, warehouse and mart models with tests and docs, history on two dims, and
`dbt build --target ci` green in CI.

## Plan (as approved)

dbt 2.0.12 in a `uv` group; project in `dbt/` with targets dev, ci and prod (prod is
Airflow's); schema override for `staging`, `warehouse`, `mart`; `persist_docs`. Staging 1:1
with lake tables (rename, cast, dedupe, defect fixes). Warehouse dims and facts for `sales`,
`finance`, `marketing` with audit columns. History on customers and products from the lake,
after a small generator extension (moves and price changes). Three marts. Tests and docs.
CI job `dbt` on three generated days.

## Decisions

- **History from the lake, not from dbt snapshots.** The generator now writes a customer
  again when they move (0.2% of existing customers a day) and a product again on each price
  change (every 30 to 120 days). `dim__sales__customers` and `dim__sales__products` turn those
  versions into `valid_from`/`valid_to`/`is_current` with window functions. A snapshot
  records build time, so a backfill would not rebuild the same history; this does.
- **Order lines are priced at the product's price on the order day** (generator), so
  `fact__sales__order_items` joins the product version valid on that day, and the customer
  version valid at the order's timestamp (Codex review on PR #11: a move later the same day
  must not apply yet). For that to hold, the generator now lets an order name only customers
  who already exist: those created before the order day, and on the first day the base
  customers, migrated at midnight. `assert_order_customer_existed_at_order_time` checks it.
- **A move always changes the current city** (Codex review on PR #11): the destination
  excludes the city of the customer's latest version, not their first one.
  `assert_customer_versions_record_a_move` checks every version in dbt; a generator test checks
  400 days of moves, including second moves. The
  singular test `assert_order_item_price_matches_product_version` proves the history is right:
  every line's price equals its product version's price (45 days: 558 older price versions).
- **Build file renamed `dwh.duckdb`** (dev, ci, build). DuckDB names the catalog after the file;
  `warehouse.duckdb` made `warehouse.<table>` ambiguous with the `warehouse` schema. The loader
  and Makefile defaults follow (`data/dev/dwh.duckdb`).
- **Late rows at the edge of the loaded dates.** An order row held back as a late row may not
  have arrived yet, so payments or lines can point at an order that is not in
  `fact__sales__orders` yet. Those `relationships`/`not_null` tests warn instead of failing,
  with the reason in the test description. Order lines take `order_date` from their own `_dt`
  (lines arrive on the creation day), so no line is dropped.
- **Orphan product keys warn**, as documented in `generator/DEFECTS.md`.
- **The warehouse assumes the lake was loaded from the epoch (2026-01-01).** Sellers and
  campaigns are written once; a window that starts later has lines pointing at sellers it never
  loaded (tried: 2026-05-15 to 06-28 fails four relationship tests). Airflow's `catchup=True`
  (M7) loads from the epoch.
- **No dbt packages.** Two generic tests in `macros/tests.sql` (`unique_combination`,
  `scd2_valid`) and three singular tests cover what `dbt_utils` would.
- **Fusion-style test syntax** (`arguments:` under each generic test) works on dbt 2.0.12.
- **All tables, no incremental models yet**: a full build of 45 days takes seconds. Incremental
  models come when a build gets slow.

## Done

- `make dbt-ci` (3 days from 2026-01-01) → `Summary: 115 total | 110 success | 5 warn`
  (31 models, 84 tests; warns: orphan keys and late rows at the edge).
- 45 days (2026-01-01 to 02-14) with `DBT_DUCKDB_PATH=../data/long/dwh.duckdb` → same summary;
  250 older customer versions (239 customers), 558 older price versions.
- `persist_docs`: 0 of 145 warehouse and mart columns without a comment
  (`select count(*) filter (where comment is null) from duckdb_columns() where schema_name in
  ('warehouse','mart')`).
- `uv run pytest -q` → 99 passed (generator tests for moves, repricing and order-day prices;
  golden checksums regenerated for the new output).

## Open

- M5 adds the naming, bundle, layer and audit-column checkers over these models.
- M7 runs `dbt build --target prod` from Airflow after `load_lake`.
