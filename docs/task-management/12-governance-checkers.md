# 12: M5 governance checkers (naming, bundle, layers, audit columns, gateway-only)

## Goal

PLAN section 11, row M5 (layers and naming in section 4, audit columns in section 7, checker
table in section 9): five blocking checkers over the dbt project and the repository. Done when
a deliberately bad model fails each checker, and the current repository passes all five.

## Plan (as approved)

The owner pre-approved autonomous work on M5 (and M6 if time allows) for one night, with the
plan written here instead of in chat.

1. `helpers/dbtlib.py`: read the dbt project statically. Refs and sources from the Jinja
   calls, YAML entries from `models/**/*.yml`, output columns from the final SELECT.
2. Five checkers in the existing style (`check()` returns errors, `report()` prints them):
   `check_naming`, `check_bundle`, `check_layers`, `check_audit_columns`, `check_gateway_only`.
3. One test file per checker with bad inputs, built from a small good dbt project
   (`tests/governance/dbt_project.py`) that each test breaks in one place.
4. Wire each checker into `ci.yml` (governance job, `if: success() || failure()`),
   `make checks` and the AGENTS.md checks table; write the model and column rules down.
5. If the repository fails a checker, fix the models or record the rule change here.

## Decisions

- **Output columns come from DuckDB's own parser, not a new dependency.** `dbtlib.render`
  reduces the Jinja to plain SQL (a ref becomes the model name, `dbt_audit_columns()` becomes its
  two columns, any other macro call becomes `null`), and `json_serialize_sql` returns the parse
  tree, from which the final select list gives each column's alias or name. It handles DuckDB
  syntax (`qualify`, lambdas, `filter`) that a generic SQL parser might not, and needs no
  database or upstream tables. As a result a final `select *` or an unaliased expression is an
  error (`check_bundle`), because its columns cannot be known statically. No model in the repo
  had either.
- **Jinja branches are expanded, not stripped** (Codex review on PR #13). Each
  `{% if %}`/`{% elif %}`/`{% else %}` combination is rendered and parsed on its own (at most
  64); every variant must be one SELECT with the same columns, so a target-conditional pair of
  SELECTs that disagree fails instead of being read from its first branch. An
  `is_incremental()` filter passes (`{{ this }}` and `{{ config() }}` are rendered too).
  A `{% for %}` loop fails: its output cannot be known without running Jinja.
- **Column naming rules** (`.agents/rules/dbt.md`, reasons in `history/dbt.md`): snake_case
  with one `_` between words (`__` stays the name-part separator); a leading `_` only for the six
  audit columns; no bare generic names (`id`, `name`, `date`, `status`, ...); a money column
  (a word such as `amount`, `price`, `fee`, `revenue`, `tax` in its name) ends in `_idr` or
  `_pct` unless its last word says it is not a measure (`refund_reason`, `spend_date`,
  `payment_method`). `_at`/`_date`/`is_` conventions are written down but not checked: that
  needs column types, so a database.
- **Key test on the grain** means a column with both `unique` and `not_null`, or a model-level
  `unique_combination` (our macro, used by staging models whose grain is a pair). `unique` alone
  allows a null key, so it does not count.
- **Staging is 1:1 with a lake table** is checked in `check_layers`: a staging model reads
  exactly `source('lake', '<source>__<table>')` matching its own name, and the table is declared
  in `_sources.yml`.
- **Audit columns, three layers.** Lake tables are read from a real file: by default the checker
  generates and loads the epoch day (2026-01-01, when every source writes) into a temporary
  file, as `check_duckdb_compat` does; `--db` reads an existing build. It also fails when a
  declared `lake` source does not exist. Staging must pass `_dt` through (added rule: it keeps
  the partition traceable from the warehouse; all 15 staging models already did). Warehouse
  models must output `_dbt_invocation_id` and `_dbt_updated_at`; marts are not required to,
  following PLAN section 7 (all three do anyway).
- **Gateway-only: exempt design records.** `PLAN.md` and `docs/m0-findings.md` show the
  gateway's own config (provider routes and key variables) as design examples, so they are
  exempt with `infra/llm-gateway/` and `.env.example`, as are the checker and
  `tests/governance/` (bad fixtures). Only API host names and `<PROVIDER>_API_KEY` names
  count; prose such as "OpenRouter" does not. A gateway virtual key name such as
  `REASONING_API_KEY` passes.
- **Folder depth is fixed.** A model sits exactly at `models/<layer>/<domain>/`; anything
  else (an `intermediate` layer, a model directly under a layer) fails naming. PLAN's ephemeral
  shared joins will need a rule when the first one appears.
- **No model changes were needed**: the M4 project passed all five checkers as written.

## Done

- `uv run pytest -q` → 174 passed (75 new: naming 27, bundle 16, layers 9, audit columns 9,
  gateway-only 14; `uv run pytest -q tests/governance/test_check_<name>.py` each).
- Each bad-model test fails the checker it targets: a wrong prefix, domain, folder or cadence,
  a non-snake_case, generic or unitless money column (naming); missing YAML, descriptions or key
  test, a YAML column the SQL lacks, `select *` (bundle); mart reading staging, warehouse reading
  the lake, staging reading a second lake table, a ref to a missing model (layers); a lake table
  without `_source_file`/`_loaded_at`/`_batch_id`, a warehouse model without the audit macro,
  staging dropping `_dt` (audit columns); a provider host or key name in code (gateway-only).
- `make checks` → all ten checkers OK on the repository.
- `uv run python -m helpers.check_audit_columns --db data/ci/dwh.duckdb` → OK against the
  3-day CI build.
- `make dbt-ci` → `Summary: 115 total | 110 success | 5 warn` (unchanged from M4).
- `check_entry_size` → OK with AGENTS.md at 141 lines and the new `.agents/rules/dbt.md`.

## Open

- Column types (`_at` timestamp, `_date` date, `is_` boolean) are not checked; that needs a
  database or dbt's catalog. A later check could read `data/ci/dwh.duckdb` after `dbt build`.
- Ephemeral models for shared joins (PLAN section 4) have no naming rule yet.
- M6 (knowledge base, `check_knowledge`) follows in its own issue.
