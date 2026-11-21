# dbt model rules (one line each; the story is in history/dbt.md). Checked by the named checker.

1. A model sits at `models/<layer>/<domain>/<name>.sql`; staging folders are source systems, warehouse and mart folders are business domains (`check_naming`).
2. Names: `staging__<source>__<table>`, `dim__` or `fact__<domain>__<table>`, `rpt__<domain>__<table>__<cadence>`; the name's domain equals its folder (`check_naming`).
3. Cadence is one of `daily`, `weekly`, `monthly`, `quarterly`, `yearly`, `snapshot` (`check_naming`).
4. Columns are snake_case with one `_` between words; a leading `_` is only for audit columns (`check_naming`).
5. No bare generic column (`id`, `name`, `date`, `status`, `type`, `value`, `amount`, ...): say whose or which (`check_naming`).
6. A money column ends in its unit, `_idr` or `_pct`; timestamps end in `_at`, dates in `_date`, flags start with `is_` (unit checked by `check_naming`).
7. Every model has YAML in its folder, a description, every output column described, and nothing listed that it does not output (`check_bundle`).
8. The final SELECT lists its columns (no `*`) and aliases every expression, so the output can be read without a database (`check_bundle`).
9. Every model has a key test on its grain: a column with `unique` and `not_null`, or a model-level `unique_combination` (`check_bundle`).
10. Staging reads exactly its own lake table; warehouse reads staging and warehouse; mart reads warehouse and mart (`check_layers`).
11. Lake tables carry `_dt`, `_source_file`, `_loaded_at`, `_batch_id`; staging passes `_dt` through; warehouse adds `{{ dbt_audit_columns() }}` (`check_audit_columns`).
12. Only `infra/llm-gateway/` and `.env.example` name a model provider's host or key variable; code calls the gateway (`check_gateway_only`).
