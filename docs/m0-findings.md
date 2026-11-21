# M0 findings: spike on macOS arm64

Run on 2026-11-21 on a MacBook (Apple Silicon, macOS 27.2.1, 16 GB RAM), Docker Desktop
29.4.0 with an 8 GB VM. All spike code lived in a throwaway folder outside the repo; nothing
from it is committed. Secrets were read from the gitignored `.env` and never printed.

Short names used below:

- `$M`: the throwaway spike folder (outside the repo).
- `py156`, `py155`: Python 3.12 venvs with `duckdb==1.5.6` and `duckdb==1.5.5`.
- `$GW`: `http://localhost:4000`, the LiteLLM proxy started for the spike.

## 1. dbt v2 on macOS arm64 with DuckDB

**Install.** The `dbt` package on PyPI is dbt v2: a Rust core shipped as a Python extension
module (`dbt/_core.abi3.so`, Mach-O arm64), not a pure-Python dbt-core.

```bash
uv venv -p 3.12 .venv && uv pip install -p .venv --prerelease=allow dbt "duckdb>=1.5,<1.6"
.venv/bin/dbt --version          # dbt 2.0.12
file .venv/lib/python3.12/site-packages/dbt/_core.abi3.so
                                 # Mach-O 64-bit dynamically linked shared library arm64
.venv/bin/dbt system install-drivers
ls ~/Library/Caches/com.getdbt/adbc/aarch64-apple-darwin/
                                 # libadbc_driver_duckdb-1.5.4.dylib
                                 # libadbc_driver_duckdb_extended-0.21.0.dev+dbt0.0.32.dylib
dbt show --inline "select version() as v"   # v1.5.4
```

The DuckDB driver is not inside the wheel. dbt downloads it as an ADBC driver on first use
(or with `dbt system install-drivers`) into `~/Library/Caches/com.getdbt/adbc/`. The bundled
DuckDB is **1.5.4**, matching the GitHub issue cited in PLAN section 2.

**Profile** (`type: duckdb`, `path:` to the file, `database: warehouse`, `schema: main`). A
throwaway project had: a source over `lake.shop__orders` and `lake.shop__customers` (written by
a Python loader with `duckdb` 1.5.6), a seed `ref__currency`, a table model
`staging__shop__orders`, an incremental model `rpt__finance__revenue__daily`
(`delete+insert`, `unique_key: order_date`, `is_incremental()` filter), a YAML snapshot
`snap__shop__customers` (`strategy: timestamp`), `unique`/`not_null` tests, and
`+persist_docs: {relation: true, columns: true}` for all models.

```bash
python loader.py data/warehouse.duckdb 1 && dbt build --profiles-dir .
#  Succeeded seed  main_ref.ref__currency (table)
#  Succeeded model main_staging.staging__shop__orders (table)
#  Succeeded snapshot main_snapshots.snap__shop__customers (snapshot)
#     Passed test  not_null_staging__shop__orders_order_id
#     Passed test  unique_staging__shop__orders_order_id
#  Succeeded model main_report.rpt__finance__revenue__daily (incremental)
#  Summary: 6 total | 6 success
python loader.py data/warehouse.duckdb 2 && dbt build --profiles-dir .   # 6 total | 6 success
```

Checked afterwards with Python `duckdb` (read-only):

| Feature | Evidence | Result |
|---|---|---|
| Seeds | `main_ref.ref__currency` exists | pass |
| Incremental | day 1 row kept its first `built_at` (22:14:51), day 2 row added (22:14:59) | pass |
| Snapshot | customer 1: `silver` valid 11-01 to 11-02, `gold` valid from 11-02, `dbt_valid_to` null | pass |
| `persist_docs` | table comments and column comments from YAML present in `duckdb_tables()` / `duckdb_columns()` | pass |
| Double underscores | `staging__shop__orders`, `rpt__finance__revenue__daily`, `snap__shop__customers` created and queried | pass |

Two things to know for M4:

- The default `generate_schema_name` gives `main_staging`, `main_report` and so on. A
  two-line override macro (`{{ custom_schema_name or target.schema }}`) gave `staging`,
  `report`, `snapshots`, `ref`, and the build stayed green.
- At the start of each run dbt prints "downloading referenced relations": it reads source
  schemas from the file itself. No network beyond the one-time driver download was needed.

**Verdict: pass.** dbt 2.0.12 on macOS arm64, bundled DuckDB 1.5.4, all five features work.

## 2. File compatibility across loader, dbt and Auto Ontology

```bash
py156/bin/python loader.py data/warehouse.duckdb 1     # loader duckdb 1.5.6 writes the file
dbt build --profiles-dir .                            # dbt's DuckDB 1.5.4 reads and writes it
py155/bin/python m0_inspect.py data/warehouse.duckdb  # reader duckdb 1.5.5, read_only=True
# reader duckdb 1.5.5
# [('2026-11-01', Decimal('10972.50'), 10, ...), ('2026-11-02', Decimal('21472.50'), 10, ...)]
# [(1, 'silver', '2026-11-01 00:00:00', '2026-11-02 00:00:00'), (1, 'gold', '2026-11-02 00:00:00', None)]
```

The same file passed back and forth between 1.5.6 (loader), 1.5.4 (dbt, two builds) and
1.5.5 (Auto Ontology's locked version) with no error, and all tables, rows and comments read
the same in each.

The publish step from D2 was tried too: Python `duckdb` 1.5.6 attaches the warehouse
read-only, runs `COPY FROM DATABASE src TO dst` into a temp file, drops the schemas that are
not served, `CHECKPOINT`s, and renames the temp file over `data/serve/serve.duckdb` with
`os.replace`. `COPY FROM DATABASE` keeps table and column comments (checked with 1.5.5).
A plain `CREATE TABLE AS` would drop them.

**Verdict: pass.** Pin the loader to `duckdb>=1.5.5,<1.6` so all three builds stay on the
1.5 storage format (D1 stands).

## 3. Auto Ontology ingests a read-only DuckDB file

Auto Ontology was cloned at commit `f3c310c7a279fcdfadf559d3fd7cd34e976d73e0`
(2026-11-20, "Bump four backend dependencies ...") and built from its own `Dockerfile`. Only
`postgres`, `auto-ontology-migrate`, `ingestion-service` and `auto-ontology` were started; a
compose override removed the published Postgres and 3002 ports, bound 3001 to `127.0.0.1`, put
both services on the gateway's Docker network, and mounted the **directory**
`$M/data/serve` at `/data/serve:ro`.

```bash
docker compose -p m0ao -f docker-compose.yml -f m0.override.yml build auto-ontology   # 3m33s
# .env: CONNECTION_STRINGS=duckdb:///data/serve/serve.duckdb
docker compose -p m0ao -f docker-compose.yml -f m0.override.yml \
  up -d postgres auto-ontology-migrate ingestion-service auto-ontology
docker logs auto-ontology-ingestion-service
# ingest: starting (1 connection(s))
# Data ingestion finished successfully for database serve — 2 table(s), 8 column(s),
#   10 embedding row(s) in 2.2s
```

**Ingest: pass.** The connector opens the path after `duckdb://` with `read_only=True`.

**Semantic compile needs a frontend table.** The ingestion service reads
`semantic_compilation_enabled` from `frontend.configurations`, which only the frontend's
migration creates. Without it the flag falls back to `False` and chat answers "The semantic
layer hasn't been created yet". For the spike the table was created by hand with that one row;
M9 must run `frontend-migrate` (or seed the row) before the first compile.

```bash
docker exec auto-ontology-ingestion-service python -c "...urlopen(Request('http://127.0.0.1:3002/semantic/compile', method='POST'))"
# 202 {"status":"accepted"}
# Finished semantic compilation successfully for database serve: 2 table(s) compiled in 102.6s
curl -N localhost:3001/api/chat/completions -d '{"question":"What was the total revenue on 2026-11-02?"}'
# sql: SELECT SUM(revenue) AS total_revenue FROM report.rpt__finance__revenue__daily WHERE order_date = '2026-11-02'
# rows: [{"total_revenue":21472.5}]       (correct)
```

**Column comments: not read.** The published file carried a marker in the table comment and
in `revenue`'s column comment (`M0MARKERV1 ...`). After ingest and compile:

```bash
docker exec postgres sh -c 'pg_dump -U ao -d auto_ontology --data-only | grep -c M0MARKER'   # 0
psql -c "select name, description from catalog_table union all select name, description from catalog_column"
# every description is null
```

`connectors/duckdb.py` builds the catalog from `information_schema.tables` and
`information_schema.columns` without the comment. The catalog already has `description`
columns (`catalog_table`, `catalog_column`), and the Databricks connector fills them from
`DESCRIBE`. Reading `duckdb_tables().comment` and `duckdb_columns().comment` in
`get_tables`/`get_columns` would carry dbt `persist_docs` through. That is a small upstream
patch (or an overlay patch) and is listed under PLAN section 13.

**Replaced file after restart: pass, and only after restart.** The publish step renames a new
file over `serve.duckdb` (new inode). Before restarting, both processes still held the old,
deleted inode:

```bash
docker exec auto-ontology sh -c 'ls -l /proc/[0-9]*/fd | grep serve.duckdb'
# pid 34 -> /data/serve/serve.duckdb (deleted)          (same in the ingestion service, pid 7)
docker compose -p m0ao ... restart ingestion-service auto-ontology
# Data ingestion finished successfully for database serve — 3 table(s), 9 column(s) ...
psql -c "select name from catalog_table"   # now includes rpt__m0__v2_marker from the new file
docker exec auto-ontology sh -c 'ls -l /proc/[0-9]*/fd | grep serve.duckdb'
# -> /data/serve/serve.duckdb                            (no "(deleted)")
POST /semantic/compile                      # 1 table(s) compiled in 61.5s (only the new one)
```

A third publish (V3) changed only data (day 3 rows), not the schema. After restarting both
services, without a compile:

```bash
ask "What was the total revenue on 2026-11-03?"   # rows: [{"total_revenue":31972.5}] (day 3, new file)
```

Ingest runs at startup; compile does not (it runs every `INGEST_INTERVAL_HOURS` or on
`POST /semantic/compile`). So the refresh task restarts both services, and calls compile only
when the schema changed, as PLAN section 6 already says.
Mounting the directory matters: a single-file bind mount pins the old inode and would never
see the rename.

**Verdict: pass with two conditions** (restart both services after each publish, compile when
the schema changed; comments are not used until the connector reads them).

## 4. Auto Ontology through a LiteLLM proxy, all four roles

LiteLLM `ghcr.io/berriai/litellm:v1.110.2` (newest non-rc release on 2026-11-20) ran on a
Docker network shared with Auto Ontology, with this spike config (secrets from env):

```yaml
model_list:
  - model_name: openai/adw-reasoning
    litellm_params: { model: nvidia_nim/nvidia/nemotron-3.5-lightning-30b-a3b, api_key: os.environ/NVIDIA_API_KEY }
  - model_name: openai/adw-non-reasoning
    litellm_params: { model: nvidia_nim/nvidia/nemotron-3.5-lightning-30b-a3b, api_key: os.environ/NVIDIA_API_KEY }
  - model_name: openai/adw-or-chat
    litellm_params: { model: openrouter/nvidia/nemotron-3.5-lightning, api_key: os.environ/OPENROUTER_API_KEY }
  - model_name: adw-embed
    litellm_params: { model: nvidia_nim/nvidia/nemotron-3-embed-1b, api_key: os.environ/NVIDIA_API_KEY }
general_settings:
  master_key: os.environ/LITELLM_MASTER_KEY
  pass_through_endpoints:
    - path: /nvidia/rerank-8b/reranking
      target: https://ai.api.nvidia.com/v1/retrieval/nvidia/nemotron-3.5-rerank-8b/reranking
      headers: { Authorization: bearer os.environ/NVIDIA_API_KEY }
```

Auto Ontology's `.env` pointed every role at the gateway:
`*_ENDPOINT=http://llm-gateway:4000/v1`, `REASONING_MODEL=openai/adw-reasoning`,
`NON_REASONING_MODEL=openai/adw-non-reasoning`, `EMBED_MODEL=adw-embed`,
`RERANK_ENDPOINT=http://llm-gateway:4000/nvidia/rerank-8b/reranking`,
`RERANK_MODEL=nvidia/nemotron-3.5-rerank-8b`.

| Role | Command / evidence | Result |
|---|---|---|
| Reasoning, non-reasoning | `_build_client` sends the alias unchanged (`ChatOpenAI(model="openai/adw-reasoning")`), so the gateway alias must be named exactly `openai/...`. Compile and chat: gateway log `25 "POST /v1/chat/completions" 200` for one question | pass |
| Embed | ingest log `POST http://llm-gateway:4000/v1/embeddings "HTTP/1.1 200 OK"`, 10/10 rows. Through the gateway, `input_type: query` and `passage` return different vectors (`[0.0585, -0.0677, ...]` vs `[0.0858, -0.0611, ...]`), so the NVIDIA fields in `extra_body` reach NVIDIA | pass |
| Rerank via `/rerank` | Auto Ontology's own `rerank_hits` run inside its container: `HTTPStatusError 422 Unprocessable Content for url http://llm-gateway:4000/rerank` | **fail** |
| Rerank via pass-through | same call with the pass-through URL: `[{'_rerank_score': -2.05, 'text': 'revenue by day'}]`; a call without a gateway key gets 401 | pass |

Why `/rerank` fails: LiteLLM's `nvidia_nim` rerank maps `top_n` to `top_k`, and NVIDIA's
`.../reranking` endpoint rejects `top_k` with HTTP 422 and the misleading message "input
rejected by content safety screening". Captured with a local echo server as `api_base`:

```text
BODY {"model": "nvidia/nemotron-3.5-rerank-8b", "query": {"text": "daily revenue"},
      "passages": [{"text": "orders per customer"}, ...], "top_k": 3}
```

```bash
curl .../nemotron-3.5-rerank-8b/reranking -d '{..., "top_k":3}'          # 422 content safety
curl .../nemotron-3.5-rerank-8b/reranking -d '{...}'                     # 200 rankings
curl .../nemotron-3.5-rerank-8b/reranking -d '{..., "truncate":"END"}'   # 200 rankings
```

Auto Ontology always sends `top_n` on the `/rerank` shape, and `additional_drop_params`
does not apply to rerank in 1.110.2. The `nvidia_nim/ranking/...` variant goes to `/v1/ranking`,
which returns 404 for this model. This is the fallback PLAN section 13 already names for a role that fails. The pass-through keeps Auto Ontology's native NVIDIA payload
(URL ending in `/reranking` is used as-is) and still requires a gateway key. Cost of the
pass-through: LiteLLM logs and traces the call but records no tokens and no cost. Checked with
the Phoenix callback: the rerank call produced spans named `litellm_proxy_request` and
`litellm_request` with `llm.model_name = nvidia/nemotron-3.5-rerank-8b` and no token or cost
attributes, while an embed call in the same run carried `llm.token_count.total` and
`llm.cost.total`; the response header said `x-litellm-key-spend: 0.0`. NVIDIA's response does
include `usage.prompt_tokens`, but the trace does not keep the response body. Rerank is only used in
semantic compile for bridge tables (`semantic/bridge_tables.py`), so this is a small share of
calls.

**Embedding model.** `nvidia/nemotron-3.5-embed-1b` (Auto Ontology's `.env.example` default)
returned `503 Service is overloaded` on every try during the spike, from NVIDIA directly and
from OpenRouter's `:free` route. `nvidia/nemotron-3-embed-1b` worked and returns 2048
dimensions, which is what Auto Ontology's `vector(2048)` / `halfvec(2048)` column expects.
`nemotron-3.5-embed-8b` returns 4096 and would not fit.

**Verdict: pass for chat and embed; rerank needs the pass-through route instead of `/rerank`.**

## 5. OpenRouter through the gateway, and OpenRouter embeddings

```bash
curl $GW/v1/chat/completions -d '{"model":"openai/adw-or-chat","messages":[{"role":"user","content":"Reply with the single word: pong"}]}'
# {"model":"openai/adw-or-chat","content":"pong","usage":{"prompt_tokens":24,"completion_tokens":131}}
# response headers: x-litellm-response-cost: 1.68e-06
```

**Chat: pass** (`openrouter/nvidia/nemotron-3.5-lightning`). The same model is on NVIDIA as
`nvidia/nemotron-3.5-lightning-30b-a3b`, which makes it a clean pair for the M12 comparison.

OpenRouter has an embeddings API (`GET /api/v1/embeddings/models` lists 30+ models):

```bash
for m in nvidia/nemotron-3.5-embed-1b:free nvidia/nemotron-3-embed-1b:free perplexity/pplx-embed-v1-4b \
         cohere/embed-5-fast google/gemini-embedding-2 baai/bge-m3; do
  curl https://openrouter.ai/api/v1/embeddings -d "{\"model\":\"$m\",\"input\":[\"daily revenue\"],\"input_type\":\"query\"}"; done
```

| Model | Dims | Note |
|---|---|---|
| `nvidia/nemotron-3.5-embed-1b:free` | - | 503 overloaded (same backend as NVIDIA) |
| `nvidia/nemotron-3-embed-1b:free` | 2048 | provider Nvidia, cost 0 |
| `cohere/embed-5-fast` | 2048 | paid |
| `perplexity/pplx-embed-v1-4b` | 2560 | does not fit `vector(2048)` |
| `google/gemini-embedding-2` | 3072 | does not fit |
| `baai/bge-m3` | 1024 | does not fit |

`nvidia/nemotron-3-embed-1b:free` on OpenRouter honours `input_type` and returns the same
vectors as NVIDIA directly (`query`: `[0.05852215, -0.06765327, -0.0074916654]` on both;
`passage`: `[0.08584928, ...]` vs `[0.085849315, ...]`).

**Verdict: yes.** OpenRouter serves a usable embedding model, and the same one as NVIDIA, so
the fixed `adw-embed` alias can fall back between the two providers without a re-ingest.

## 6. Can Auto Ontology forward a request id or header to its model client?

**No, not at the pinned commit.** Read in the source:

- `utils/llm_invoke.py` `_build_client`: `ChatOpenAI(model, api_key, base_url, max_tokens,
  timeout, max_retries=0)`; no `default_headers`, no `extra_body`, no metadata, no callbacks.
- `utils/embedding.py`: `extra_headers` is only set when there is no API key.
- `utils/rerank.py`: fixed headers (`accept`, `Authorization`).
- `grep -rn 'request_id\|correlation\|langfuse\|opentelemetry' auto_ontology` (outside tests):
  nothing that reaches a model call. The chat API takes `conversation_id`, but it is not passed
  down to the clients.

Seen from the tracing side: one chat answer produced 22 Langfuse generations in 22 separate
traces, and in Phoenix 21 spans in 7 traces, none tied to the question. LiteLLM does return
`x-litellm-call-id` per call and logs the caller's key.

What it would take to link calls to an answer, cheapest first:

1. **Time window + caller key, no code change.** The golden runner asks one question at a
   time with the `auto-ontology` key; every gateway call between the request start and the
   `result` event belongs to that answer. Good enough for M10 if questions are serialized.
2. **Overlay patch** (small): a context variable set per chat request, passed as
   `default_headers` / `extra_body={"metadata": {"trace_id": ...}}` in `_build_client`,
   `embed_texts` and `_scores`. Whether LiteLLM then groups the calls into one Langfuse trace
   was not tested in M0.
3. **Upstream PR** with the same change, behind an env flag.

**Verdict: not possible today; M10 starts with option 1, option 2 if the window is too
coarse.**

## 7. Memory: Langfuse and Phoenix next to Auto Ontology

Measured with `docker stats --no-stream` after a chat question, each tool wired to LiteLLM as
its trace sink. Docker Desktop VM: 8 GB; host: 16 GB.

| Container | Langfuse run (MiB) | Phoenix run (MiB) |
|---|---|---|
| auto-ontology | 488 | 493 |
| auto-ontology-ingestion-service | 243 | 243 |
| postgres (Auto Ontology, pgvector) | 82 | 83 |
| LiteLLM | 654 | 662 |
| langfuse-web 4.83.0 | 760 | - |
| langfuse-worker 4.83.0 | 576 | - |
| clickhouse 26.3.62.3 | 974-1021 | - |
| minio | 134 | - |
| postgres 17 (Langfuse) | 60 | - |
| redis 7 | 9 | - |
| phoenix 22.0.0 | - | 474-621 |
| **Total** | **3,987-4,026** | **1,956-2,098** |

The tracing stack alone: **Langfuse about 2.5 GiB** (6 containers), **Phoenix about 0.5-0.6
GiB** (1 container). With Langfuse running, macOS `memory_pressure` reported 48% free.
Airflow is not in either number.

Findings that change the M8 setup:

- The current Langfuse is **v4**, not v3. The self-host compose keeps the v3 component set
  (web, worker, Postgres, ClickHouse, Redis, MinIO) and adds an optional `langfuse-ai-gateway`,
  which is not needed beside LiteLLM. Its default `TELEMETRY_ENABLED=true` must be set to
  `false`. Headless init (`LANGFUSE_INIT_*`) creates the org, project and keys.
- v4 runs in **events_only** mode: the v1 read APIs (`/api/public/traces`,
  `/api/public/observations`, `/api/public/metrics/daily`) answer "not available on deployments
  running in Langfuse v4 events_only mode". Reads use `/api/public/v2/observations`; writes go
  through OpenTelemetry. LiteLLM's `langfuse_otel` callback delivered generations with input,
  output, reasoning tokens and cost (for example `{"input":22,"output":0,"total":222,
  "output_reasoning_tokens":200}`, cost `0.00004154`).
- Phoenix 22 enables auth by default: spans were refused with 401 until
  `PHOENIX_ENABLE_AUTH=false` (spike only; M8 would set a key instead).

**Verdict: both fit.** Langfuse plus Auto Ontology plus the gateway take about 4 GiB of the
8 GB VM, leaving room for Airflow's LocalExecutor stack, but not much else. Keep D6 with
Langfuse in an `obs` compose profile that can be stopped when not needed.

## Decisions

| Decision | Status | Why |
|---|---|---|
| D1. DuckDB 1.5.x everywhere | **stands** | dbt v2 bundles 1.5.4, Auto Ontology locks 1.5.5, the loader ran 1.5.6; one file moved between all three with no error (items 1, 2) |
| D2. Published DuckDB snapshot | **stands, with conditions** | Ingest from a read-only mount works and a replaced file is picked up after restarting both services (item 3). Conditions: mount the directory, not the file; publish with `COPY FROM DATABASE` (keeps comments); after each publish restart `auto-ontology` and `ingestion-service`, and `POST /semantic/compile` when the schema changed; seed `semantic_compilation_enabled`. Postgres fallback not needed |
| D5. LiteLLM in front of every call | **stands, two changes** | Chat and embed work with `openai/` aliases and the NVIDIA `input_type` field (item 4); OpenRouter chat works (item 5). Changes: rerank uses a LiteLLM pass-through route, not `/rerank` (LiteLLM's `top_k` mapping is rejected by NVIDIA); the embedding alias uses `nvidia/nemotron-3-embed-1b` (2048 dims, on NVIDIA and OpenRouter with identical vectors) because `nemotron-3.5-embed-1b` was overloaded on both |
| D6. Langfuse self-hosted | **stands, updated** | Langfuse v4.83.0 takes about 2.5 GiB and fits beside Auto Ontology on an 8 GB Docker VM (item 7). Use the `langfuse_otel` callback and the v2 read API; Phoenix 22 (about 0.6 GiB) stays the fallback |

Also found: Auto Ontology cannot forward a request id (item 6), and does not read DuckDB
column comments (item 3). Both go to PLAN section 13 with the workaround.

## Version pins found

| Component | Pin |
|---|---|
| dbt v2 | PyPI `dbt==2.0.12` (Rust core, `_core.abi3.so` arm64) |
| dbt DuckDB driver | ADBC `libadbc_driver_duckdb-1.5.4` (DuckDB v1.5.4), downloaded by dbt |
| Loader DuckDB | Python `duckdb>=1.5.5,<1.6` (spike used 1.5.6) |
| Auto Ontology | `NVIDIA/auto-ontology@f3c310c7a279fcdfadf559d3fd7cd34e976d73e0`, locks `duckdb==1.5.5` |
| Auto Ontology Postgres | `pgvector/pgvector:pg17` (`sha256:b513c48566e4...`) |
| LiteLLM proxy | `ghcr.io/berriai/litellm:v1.110.2` (`sha256:ef798594ca3d...`) |
| Langfuse | `docker.langfuse.com/langfuse/langfuse:4.83.0` (`sha256:a91445265d1f...`), `langfuse-worker:4.83.0` (`sha256:a6eac4bb99df...`), compose from tag `v4.83.0` |
| Langfuse dependencies | `clickhouse/clickhouse-server:26.3.62.3`, `postgres:17`, `redis:7`, `cgr.dev/chainguard/minio` (untagged upstream; pin by digest `sha256:e9cf6b99c226...`) |
| Phoenix (fallback) | `arizephoenix/phoenix:version-22.0.0` (`sha256:13b1575c5e02...`) |
| Chat model | NVIDIA `nvidia/nemotron-3.5-lightning-30b-a3b`; OpenRouter `nvidia/nemotron-3.5-lightning` |
| Embedding model | `nvidia/nemotron-3-embed-1b` (2048 dims); OpenRouter `nvidia/nemotron-3-embed-1b:free` |
| Rerank model | `nvidia/nemotron-3.5-rerank-8b` at `ai.api.nvidia.com/v1/retrieval/nvidia/nemotron-3.5-rerank-8b/reranking` |

Image digests are shortened here; M1/M8 record the full digests in the compose files.
