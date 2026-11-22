# 24: Schemas take the layer names: data_lake_layer, data_staging_layer, data_warehouse_layer, data_mart_layer

## Goal

The owner saw `analytics.mart` and `analytics.warehouse` in Auto Ontology after the dbt folders
were renamed to `data_<layer>_layer` (#16) and asked for one official name per layer. Done when
the checks, `make dbt-ci` and the tests pass, a 7-day backfill writes only the new schemas, and
Auto Ontology lists `analytics.data_mart_layer` and `analytics.data_warehouse_layer` with
`make ontology-check` passing.

## Plan (as approved)

Issue created on the owner's request on 2026-11-22 ("ops tetap, analytics tetap"), started after
#23 was merged.

1. dbt: `+schema` per layer, `schema:` of the 15 lake sources.
2. Loader, checkers, pipeline (gate, recorder, snapshot, ontology-check) and their tests.
3. Knowledge entries, doc blocks, PLAN, AGENTS.md, rules.
4. Rebuild from empty files; Auto Ontology re-ingests and recompiles.

## Decisions

- **Schema = layer folder**, enforced: `check_naming` now fails when a layer's `+schema` in
  `dbt_project.yml` differs from its folder or a lake source is not in `data_lake_layer` (rule
  14). The registry `.agents/rules/dbt-naming.yaml` says so beside the folder list.
- **Unchanged by the owner's decision:** `ops` (the run log is not a layer) and the serving catalog
  `analytics` (the snapshot's file name).
- **The dbt source keeps the name `lake`.** `source('lake', '<table>')` is a dbt label, not a
  schema; renaming it would touch every staging model and the layer rule for no reader-visible
  gain. Its `schema:` is `data_lake_layer`.
- **The dbt project keeps the name `warehouse`** (test ids read `model.warehouse.<model>`); it is
  not a schema.
- **History stays history:** worknotes of earlier issues, the M3 row in PLAN's milestone table and
  `de-0002` (why the build file is `dwh.duckdb`) keep the old names they were written with.
- **Doc blocks:** lineage lines now read `data_lake_layer.<table>` and the layer labels in the
  trees are schema names.
- **ClickHouse ceiling raised to 3 GiB.** After two full compiles' traces were stored, ClickHouse's
  RSS reached 1.75-2.2 GiB and the 1.5 GiB cap from M9 made Langfuse reads fail again ("memory
  limit exceeded"). The cap is now a ceiling, not a squeeze; the caches stay small. All three
  profiles together measured 5.00 GiB afterwards.
- **ontology-check signs in on `localhost`.** The edge redirects 127.0.0.1 to localhost (M9 review
  fix), and urllib turns a redirected POST into a GET, so sign-in on 127.0.0.1 answered 404.
- **Rebuild without deleting:** the old Airflow build file, its artifacts and snapshots were
  moved to `data/{build,artifacts,serve}.pre-issue24/`, not deleted; a loader run on the old file
  would have left both schemas side by side. Auto Ontology's catalog volume (`wh_ao-db`, derived
  data created in M9) was dropped so no table with an old schema name lingers in its catalog; the
  admin login is recreated by its migration.

## Done

- `make dbt-ci` from an empty file -> `Summary: 115 total | 110 success | 5 warn` (unchanged);
  tables only in `data_lake_layer` (15), `data_warehouse_layer` (13), `data_mart_layer` (3), views in
  `data_staging_layer` (15).
- Every SQL block of `da-0001` to `da-0005` runs on the new build.
- Airflow, empty build file: `make backfill FROM=2026-01-01 TO=2026-01-07` -> every day passed;
  schemas `data_lake_layer`, `data_warehouse_layer`, `data_mart_layer` and `ops`, nothing else;
  refresh `skipped` on all seven (ontology profile down during the backfill, as intended).
- `make up-ontology` on a fresh catalog: compile of 16 tables in 546s; Auto Ontology's catalog
  holds `data_mart_layer` (3 tables) and `data_warehouse_layer` (13), every one with a description.
- `make ontology-check DAY=2026-01-06` -> `PASS`: `SELECT net_revenue_idr FROM
  data_mart_layer.rpt__finance__revenue__daily WHERE revenue_date = '2026-01-06'` -> 964,863,561,
  equal to the snapshot; 10 calls with the `auto-ontology` key in the gateway log and 10 Langfuse
  generations; both containers without internet.
- 2026-01-08 through Airflow with the ontology profile up -> `passed`, snapshot schemas
  `data_mart_layer` and `data_warehouse_layer`, refresh `passed` in 121s.
- `uv run pytest -q` -> 297 passed (two new naming tests); `make checks` -> all eleven OK.

## Open

- Delete `data/*.pre-issue24/` once the owner no longer needs the old build.
