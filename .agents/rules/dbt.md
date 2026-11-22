# dbt model rules (one line each; the story is in history/dbt.md). Checked by the named checker.

1. One folder per table: `models/<layer folder>/<table>/<table>.{sql,yml,md}`; layer folders from `dbt-naming.yaml`; no SQL in the lake folder (`check_naming`).
2. Names: lake `<source>__<table>`, `staging__<source>__<table>`, `dim__`/`fact__<domain>__<table>`, `rpt__<domain>__<table>__<cadence>` (`check_naming`).
3. Cadence is one of `daily`, `weekly`, `monthly`, `quarterly`, `yearly`, `snapshot` (`check_naming`).
4. Columns are snake_case with one `_` between words; a leading `_` is only for audit columns (`check_naming`).
5. Model columns have two or more words and end in a class word from `dbt-naming.yaml`, or start `is_`/`has_`; staging renames lake columns (`check_naming`).
6. A money column ends in its unit, `_idr` or `_pct`; timestamps end in `_at`, dates in `_date` (unit checked by `check_naming`, types not yet).
7. Every model's YAML is `<table>.yml` beside it, its description is `{{ doc("<table>") }}`, every output column is described, and nothing listed that it does not output (`check_bundle`).
8. One SELECT that lists its columns (no `*`), aliases every expression, and keeps them the same in every `{% if %}` branch; no `{% for %}` (`check_bundle`).
9. Every model has a key test on its grain: a column with `unique` and `not_null`, or a model-level `unique_combination` (`check_bundle`).
10. Staging reads exactly its own lake table; warehouse reads staging and warehouse; mart reads warehouse and mart (`check_layers`).
11. Lake tables carry `_dt`, `_source_file`, `_loaded_at`, `_batch_id`; staging passes `_dt` through; warehouse adds `{{ dbt_audit_columns() }}` (`check_audit_columns`).
12. Only `infra/llm-gateway/` and `.env.example` name a model provider's host or key variable; code calls the gateway (`check_gateway_only`).
13. Every table, lake included, has `<table>.md`: one docs block, an opening paragraph, then the `doc_sections` of `dbt-naming.yaml` in order (`check_bundle`).
14. A layer's DuckDB schema has its folder's name (`+schema` in dbt_project.yml, `schema:` of lake sources); `ops` keeps its own (`check_naming`).
