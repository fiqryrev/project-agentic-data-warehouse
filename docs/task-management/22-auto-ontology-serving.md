# 22: M9 publish snapshot, Auto Ontology at pinned SHA wired to the gateway, refresh task

## Goal

PLAN section 11, row M9 (D2, sections 6 and 8.1): Auto Ontology serves a published snapshot of
`warehouse` and `mart`, refreshed by the daily DAG, with every model call through the gateway.
Done when the chat answers a revenue question correctly (checked against SQL on the snapshot) and
every model call it made is in the gateway log.

## Plan (as approved)

Approved in chat on 2026-11-22, including the unauthenticated rerank route and real model calls.

1. `infra/auto-ontology/`: `UPSTREAM_SHA`, a bootstrap that clones upstream at that commit into a
   gitignored folder and applies one overlay patch (the DuckDB connector reads comments).
2. Profile `ontology`: pgvector Postgres, migrations, ingestion service, backend, frontend;
   `data/serve/` mounted read-only as a directory; an internal network whose only way out is the
   gateway; every model role on the gateway with the `auto-ontology` key.
3. DAG tasks 5 `publish_snapshot` and 6 `refresh_ontology` (socket proxy limited to two restarts;
   skipped when the profile is down); snapshot hash in `ops.run_log`.
4. ClickHouse memory capped so core, obs and ontology fit together.
5. `make up-ontology`, `make down-ontology`, `make ontology-check`; static tests.

## Decisions

- **Upstream had no new commit** after `f3c310c7a279` (M0's), so that SHA is pinned. The bootstrap
  resets the clone to it before applying `patches/*.patch`; images are tagged with the SHA.
- **Overlay patch 0001** (60 lines, `connectors/duckdb.py` only): `get_tables` and `get_columns`
  join `duckdb_tables()` / `duckdb_columns()` and return the comment as `description`, a column the
  connector contract already accepts (`catalog/normalize.py`). Result: 16 of 16 table and 145 of
  145 column descriptions in Auto Ontology's catalog (M0 had none). Worth offering upstream.
- **No route out for Auto Ontology.** Its containers are only on `wh-ontology` (`internal: true`);
  the gateway joins it. Docker publishes no port of a container that is only on an internal
  network, so an nginx (`ao-edge`) on both networks publishes the UI.
- **The backend port is not published (changed from the plan).** The plan had the API on
  127.0.0.1:3100. Probing it showed the backend answers `/api/chat/completions` with no
  authentication (200), while the frontend refuses without a session (401): the backend trusts
  the frontend. Publishing it would bypass Auto Ontology's auth, so only the UI is published and
  scripts sign in through it (`/api/auth/sign-in/email`) like a browser.
- **Rerank takes no key** (approved): the pass-through route is `auth: false`, reachable only on
  the private networks and 127.0.0.1; the gateway still logs and traces it, without a caller.
- **NVIDIA aliases carry a price.** The first NVIDIA calls logged no cost (`x-litellm-response-cost`
  empty): LiteLLM has no price for the model on NVIDIA, so Auto Ontology's spend would read $0
  and its budget would never trip. The aliases now carry the OpenRouter list price of the same
  model ($0.07 / $0.20 per million input / output tokens, from the M8 smoke) as an estimate.
- **`openai/adw-non-reasoning` really is non-reasoning now.** Probing the same question: default
  937 reasoning tokens, `reasoning_effort: low` 1,152, `chat_template_kwargs.enable_thinking:
  false` 0. The alias sets the last; before, both aliases reasoned.
- **Compile:** the flag `semantic_compilation_enabled` is opt-in upstream (a missing row is off);
  `ao-seed` inserts it after the frontend migration and leaves an existing value alone. The
  ingestion service ingests and compiles once at every start, and the pass only compiles what is
  new (M0), so `refresh_ontology` restarts both services and waits on `/semantic/status` for a
  success newer than the restart instead of triggering a second pass.
- **Snapshot:** `COPY FROM DATABASE` from the build file into a temporary file, every schema but
  `warehouse` and `mart` dropped, row counts compared with the build, dated copy kept (last 7),
  then `analytics.duckdb` replaced by an atomic rename. The file name makes the catalog name
  `analytics`. Comments survive (16/16 tables, 145/145 columns).
- **`ops.run_log`** gains `snapshot_hash_code` and `ontology_refresh_status`; a day whose gate
  passed but whose snapshot was not published, or whose refresh failed, is `failed`.
- **ClickHouse cap 1.5 GiB, not 1 GiB.** At 1 GiB every Langfuse read failed: ClickHouse holds
  about 1.14 GiB after start, so queries hit "memory limit exceeded". At 1.5 GiB it idles at
  about 1.58 GiB RSS, and the three profiles together use 5.2 GiB of the 7.75 GiB VM.
- **Socket proxy:** `wollomatic/socket-proxy:1.13.1` (August; 1.14.0 was a day old), allowing
  only `POST /containers/wh-(auto-ontology|ingestion-service)-1/restart` from
  `airflow-scheduler`, and `GET /_ping`.
- **ontology-check tries the question twice.** One run in M9 ended without SQL (rows null), then
  the same question answered correctly; the chat is an LLM agent. The check reports the attempt.
- **Langfuse reads need a time bound:** without `toStartTime` Langfuse 4.83 answers 422 "narrow
  your request" once a compile's traces are in the project. The gateway's `/spend/logs` with a
  date range sums per key unless `summarize=false`.

## Done

- `make up-obs`, `make up-ontology`: all containers healthy; the first ingest read 16 tables, 145
  columns, 161 embedding rows in 5.0s; the first compile: 16 tables in 525s, 5 semantic FK edges.
- `make ontology-check` -> `PASS` (2026-01-05 and 2026-01-08):
  - answer: `SELECT net_revenue_idr FROM mart.rpt__finance__revenue__daily WHERE revenue_date =
    '2026-01-08'` -> 901,257,780, equal to the same SQL on the snapshot; the prose answer adds
    "net of refunds and PPN", text that comes from the dbt doc blocks;
  - gateway: 10 calls with the `auto-ontology` key in the spend log (`adw-embed`,
    `openai/adw-reasoning`, $0.001333), 10 matching Langfuse generations, no other caller;
  - egress: from both Auto Ontology containers `1.1.1.1:443` is unreachable ("Network is
    unreachable") and DNS for public names fails, while the gateway answers.
- Airflow, all three profiles up: `make backfill FROM=2026-01-08 TO=2026-01-08` -> passed;
  `publish_snapshot` 16 tables, 26,666 rows; `refresh_ontology` restarted both services, ingest and
  compile finished in 136s; `ops.run_log` row `passed`, snapshot hash `28b1fe858cc2`, refresh
  `passed`. Net revenue for 2026-01-05 moved from 718,545,885 to 718,490,209 after the 8th was
  loaded: a refund is booked on the payment day (doc block of `rpt__finance__revenue__daily`).
- Socket proxy from the scheduler: restart of `wh-ao-db-1`, stop of the gateway, container list
  and container create all 403.
- Spend: the `auto-ontology` key reads $0.056 after the first compile, the refresh and four
  questions. The first compile partly ran before the NVIDIA price was set, so that is a lower bound.
- Memory with core, obs and ontology up (`docker stats`): 5.20 GiB in all.
- `uv run pytest -q` -> 292 passed (`tests/pipeline/test_ontology.py` new, snapshot and refresh
  tests added); `make checks` -> all eleven OK.

## Open

- **FK detection runs out of tokens.** The first compile logged 112 `LengthFinishReasonError`
  (the reasoning model spent all 8,192 tokens of `FkAndPkResult` thinking on wide tables), so some
  FK suggestions are missing. Options: a non-reasoning model for that step (an upstream setting or
  a second overlay patch), or a larger `max_tokens`. Compile still succeeds.
- Offer the comments patch upstream.
- Per-answer traces and the `ask` client (M10); the gateway's NVIDIA price is an estimate until
  NVIDIA's own rate is known.
