# project-agentic-data-warehouse: design and implementation plan

Date: 2026-11-21 (rev 3) | Status: draft for owner review | Planner: Fable 5.2 | Implementer: Opus
Repository: https://github.com/fiqryrev/project-agentic-data-warehouse

Rev 3 adds: LLM observability and tracing (section 8), a model gateway that makes the provider
swappable (NVIDIA, OpenRouter, others), human-in-the-loop labeling of answers, and the harness
additions agreed after rev 2 (section 9).

## 1. Intent

A single-node, end-to-end data warehouse that runs on a MacBook with Docker and is built to be
operated by coding agents:

```
source data -> data lake (Parquet + DuckDB) -> staging -> warehouse (dim/fact) -> mart (rpt)
      -> published read-only snapshot -> NVIDIA Auto Ontology (ontology, text-to-SQL, MCP)
                 all of it triggered daily by Airflow, transformed by dbt v2
      every model call -> LLM gateway -> provider; traced, costed, and reviewed by a person
```

The warehouse is the subject. The way it is run is the point: one map for agents, rules with
reasons, a distilled knowledge base, full traceability of data and of model calls, and checks
that block a bad change.

### Goals
- `make up` on a laptop gives a working daily batch and a chat that answers business questions
  with the SQL behind each number.
- Every number, table and decision can be traced: to its source file, its run, its commit, its
  issue and the lesson learned from it.
- Every model call is recorded with model, provider, tokens (input, output, reasoning), cost,
  latency and which job made it. Spend per day and per job is a query, not a guess.
- The model provider is swappable by editing one config file, and a swap is judged on the same
  question set for accuracy, cost and latency.
- A person can mark any answer right or wrong, say why, and give the correct answer; those labels
  improve the question set, the knowledge base and the ontology.
- Every rule that matters is a blocking check, not prose.
- Reproducible and portable: pinned versions, relative paths, everything in Compose.

### Non-goals
- No hosting in v1. No cloud storage, Kubernetes, CeleryExecutor or streaming.
- No fork of Auto Ontology. It is consumed at a pinned commit and observed from the outside.
- No Prometheus or Grafana in v1. Pipeline health is modelled as warehouse tables.

### Anti-goals
- Random, meaningless data. The ontology is built from names, keys and sample values.
- An agent or the ontology service holding any write path to the warehouse.
- A model call that bypasses the gateway, and so is neither counted nor traced.
- An accuracy claim with no labeled evidence behind it.
- A rule, a lesson or a lineage claim that exists only in someone's head.

## 2. Facts verified on 2026-11-21 (re-check before pinning)

| Fact | Source | Consequence |
|---|---|---|
| dbt v2 (2.0.0, Sept 2026) is a Rust binary on the Fusion engine with a built-in DuckDB adapter | duckdb.org/2026/09/22/dbt-fusion | Use dbt v2, no `dbt-duckdb` Python package |
| dbt v2 ships a pinned DuckDB driver (a GitHub issue reports 1.5.4); it cannot load extensions and may fail to infer flat-file schemas | datapace.ai/blog/dbt-v2-duckdb-adapter, dbt-labs/dbt#16897 | dbt never reads files. A Python loader fills the lake tables first |
| DuckDB 2.0.1 LTS is the newest release. Files created by 2.0 cannot be read by versions before 2.0 | duckdb.org/2026/10/21/announcing-duckdb-200 | The file format must stay readable by 1.5.x |
| Auto Ontology pins `duckdb>=1.5.5`, opens `duckdb://<path>` read-only, caches connectors | auto-ontology `connectors/duckdb.py`, `registry.py`, `uv.lock` | Three DuckDB builds touch the data (D1) |
| DuckDB allows one read-write process or many read-only processes on a file, not both | DuckDB concurrency docs | Auto Ontology never opens the file dbt writes (D2) |
| DuckDB connections work only through `CONNECTION_STRINGS`, not the UI | auto-ontology `docs/connections.md` | Connection is set in `.env` |
| Auto Ontology reads four model roles from env: `REASONING_*`, `NON_REASONING_*`, `EMBED_*`, `RERANK_*`, each with its own endpoint, key and model | auto-ontology `.env.example`, `utils/model_config.py` | Every role can point at a gateway URL without code changes |
| Chat client choice depends on the model name: `openai/`, `azure/`, `aws/` prefixes use `ChatOpenAI`; anything else uses `ChatNVIDIA` | auto-ontology `utils/llm_invoke.py` `_build_client` | Gateway aliases are named `openai/<alias>` so the standard OpenAI client is used; the alias is sent unchanged, so the gateway model name is literally `openai/<alias>` (verified in M0) |
| Embeddings use the OpenAI `/embeddings` API plus NVIDIA fields in `extra_body` (`input_type`); ingest and query must use the same embedding model | auto-ontology `utils/embedding.py`, `.env.example` | Changing the embedding model means a full re-ingest; keep it fixed while chat models are swapped |
| Rerank posts `{"query", "documents", "top_n"}` when the URL ends in `/rerank`, NVIDIA's own shape otherwise | auto-ontology `utils/rerank.py` | LiteLLM's `/rerank` sends `top_k`, which NVIDIA rejects (M0); the gateway uses a pass-through route ending in `/reranking`, which Auto Ontology calls with NVIDIA's native shape |
| The chat API returns the answer, SQL, rows and a step trace (`thoughts`), and accepts an optional `conversation_id` | auto-ontology `docs/conversation-api.md` | Our own client can record full answer traces |
| Ingestion service: ingest at startup, then every `INGEST_INTERVAL_HOURS`; `POST /semantic/compile` on port 3002, unauthenticated | auto-ontology `ingestion_service/router.py` | Airflow triggers compile on the private network; 3002 never published |
| Airflow 3.3.x docs exist; official compose defaults to CeleryExecutor | airflow.apache.org | Own slim compose with LocalExecutor |

Checked in M0 (`docs/m0-findings.md`, 2026-11-21): dbt v2 is PyPI `dbt==2.0.12` and bundles
DuckDB 1.5.4; LiteLLM v1.110.2 carries chat and embed for Auto Ontology, but its NVIDIA rerank
mapping sends `top_k`, which NVIDIA rejects, so rerank goes through a pass-through route; the
current Langfuse is v4.83.0 (about 2.5 GiB idle on the laptop, Phoenix about 0.6 GiB);
OpenRouter serves `nvidia/nemotron-3-embed-1b` with the same vectors as NVIDIA; Auto Ontology
cannot forward a request id or header to its model client, and does not read DuckDB column
comments.

## 3. Decisions

**D1. DuckDB 1.5.x everywhere in v1, not 2.0.** dbt v2 bundles its own pinned DuckDB and Auto
Ontology locks 1.5.5; a 2.0-format file would be unreadable by both. A CI check asserts all
three builds can open the same file. Move to 2.0 when both ship it.

**D2. Serving: a published DuckDB snapshot.** Airflow copies the `data_warehouse_layer` and `data_mart_layer` schemas
into a new file (`COPY FROM DATABASE`, which keeps comments), renames it atomically into
`data/serve/`, and Auto Ontology mounts the directory read-only (a single-file mount would pin
the old inode). Both Auto Ontology services cache the open file, so the refresh task restarts
`auto-ontology` and `ingestion-service` after each publish (verified in M0). Fallback if this
ever fails: publish the same tables to Postgres.

**D3. Data: deterministic generator first, open dataset as an optional second domain.**

**D4. Local first.** Hosting is deferred; section 12 lists what keeps a later move cheap.

**D5. One LLM gateway in front of every provider: LiteLLM proxy.** OpenAI-compatible, routes to
NVIDIA, OpenRouter, OpenAI, Anthropic, local models and others; records tokens and cost per
call; enforces budgets; sends traces to Langfuse. Auto Ontology is configured with gateway
aliases, never with a provider URL. M0: chat and embed use OpenAI-compatible aliases; rerank uses
a LiteLLM pass-through route to NVIDIA's native endpoint, because LiteLLM v1.110.2 maps `top_n`
to `top_k` and NVIDIA rejects it. Alternatives: calling providers directly (no single place to
count or swap), or OpenRouter alone as the gateway (one vendor, no local tracing, no budget
control of our own).

**D6. Tracing and labeling: Langfuse, self-hosted.** Traces, cost dashboards, scores, annotation
queues for human review, datasets and experiment comparison in one open-source tool. Cost:
self-hosting needs its own Postgres, ClickHouse, Redis and object storage. Lighter fallback:
Arize Phoenix, one container, with traces, annotations and datasets but fewer review workflows.
M0 measured Langfuse v4.83.0 at about 2.5 GiB and Phoenix 22 at about 0.6 GiB beside Auto
Ontology; Langfuse fits, so it stays. Traces go in through LiteLLM's `langfuse_otel` callback;
Langfuse v4 serves reads from the v2 API only.

## 4. Layers and naming

One DuckDB file, four schemas named after the dbt layer folders (issue 24), plus `ops` for the
run log. Table names carry the layer too.

| Layer | Schema | Table name | Built by | Example |
|---|---|---|---|---|
| Data lake | `data_lake_layer` | `<domain>__<table_name>` | Python loader, append-only by `dt` | `shop__orders` |
| Staging | `data_staging_layer` | `staging__<domain>__<table_name>` | dbt, view | `staging__shop__orders` |
| Warehouse | `data_warehouse_layer` | `dim__<domain>__<table_name>`, `fact__<domain>__<table_name>` | dbt, table or incremental | `fact__sales__order_items` |
| Mart | `data_mart_layer` | `rpt__<domain>__<table_name>__<cadence>` | dbt, table | `rpt__finance__revenue__daily` |

Rules (each enforced by a checker):
- `<domain>` in lake and staging is the **source system** (`shop`, `ledger`, `marketing`,
  `gateway`, `langfuse`). In warehouse and mart it is the **business domain** (`sales`,
  `finance`, `marketing`, `ops`).
- Cadence is one of `daily`, `weekly`, `monthly`, `quarterly`, `yearly`, `snapshot`.
- Staging is 1:1 with a lake table: rename, cast, dedupe, nothing else.
- Lineage only flows downward: staging reads lake; warehouse reads staging and warehouse;
  mart reads warehouse and mart.
- No separate intermediate layer. A shared join that is not a dim or fact is an ephemeral dbt
  model, never a table.
- Every lake and warehouse row carries audit columns (section 7).
- One folder per table under four layer folders: `dbt/models/data_lake_layer/`,
  `data_staging_layer/`, `data_warehouse_layer/`, `data_mart_layer/`. The table folder is named
  after the table and holds `<table>.sql`, `<table>.yml` and `<table>.md` (lake folders hold no
  SQL: the loader builds them). The `.md` is the table's doc block (opening paragraph, then
  Potential Analyses, Grain, Table Lineage, Units and Conventions, Known Caveats, Refresh
  Cadence, Change History) and the YAML description points to it, so it is what `persist_docs`
  writes into the comment Auto Ontology reads.
- Model columns end in a class word (`_id`, `_key`, `_code`, `_number`, `_name`, `_address`,
  `_status`, `_type`, `_at`, `_date`, `_idr`, `_pct`, `_count`, `_quantity`) or start with
  `is_`/`has_`; lake columns keep the source's names and staging renames them. The registry is
  `.agents/rules/dbt-naming.yaml`.

Auto Ontology sees `data_warehouse_layer` and `data_mart_layer` only. The `ops` domain (pipeline runs, model calls,
labels) goes through the same layers as business data, so the chat can answer questions about
the platform itself, for example "what did reasoning calls cost last week".

## 5. Data

| Option | What | For | Against |
|---|---|---|---|
| **A. Deterministic generator (pick)** | Python code, seeded by `(seed, date)`, one Parquet partition per table per day | New data every day; no licence or account; defects are deliberate and documented; any day regenerates byte-for-byte | Distributions are designed, not real |
| B. Open dataset, replayed | Olist Brazilian E-Commerce (about 100k orders, 9 tables, Kaggle), dates shifted so each run receives one more day | Real relational shapes and mess | Kaggle account; licence reported as non-commercial (confirm), so data cannot be committed; the replay ends |
| C. Benchmark data | TPC-H or TPC-DS generated by DuckDB | One command, any size | Artificial names and values; weak subject for an ontology |

An agent writes and maintains the generator code and its small committed reference files. A
model does not generate rows at run time.

**v1:** a fictional Indonesian marketplace with source systems that disagree on purpose.
- `shop`: customers, sellers, products, categories, orders, order_items, payments, shipments,
  refunds, vouchers.
- `ledger`: invoices, invoice_lines, settlements; revenue net of refunds and tax, a different
  customer key, a different status vocabulary.
- `marketing`: campaigns, daily spend.
- Documented defects: casing, duplicates, late rows, orphan keys, a status renamed mid-history.

Platform sources, landed daily by the same loader:
- `gateway`: one row per model call (from the LiteLLM spend log).
- `langfuse`: traces, observations, scores and annotations (from its export API).

**Later:** Olist as an extra domain `olist`.

## 6. Architecture (local)

```
 MacBook, Docker Desktop, one network "wh", every published port bound to 127.0.0.1
 Compose profiles: core | ontology | obs   (start only what the day needs)

 airflow (core)                                auto-ontology (ontology, upstream @ pinned SHA)
 ┌─────────────────────────────────────┐       ┌───────────────────────────────────┐
 │ DAG warehouse_daily                 │       │ frontend :3000, backend, ingest,  │
 │ 1 generate_source -> landing/       │       │ mcp, postgres+pgvector            │
 │ 2 load_lake       -> data_lake_layer│       └──────┬───────────────▲────────────┘
 │ 3 dbt build       -> staging..mart  │   model calls│               │ duckdb (read-only)
 │ 4 quality_gate                      │              ▼               │
 │ 5 publish_snapshot ─────────────────┼──────► data/serve/analytics.duckdb
 │ 6 refresh_ontology                  │       ┌───────────────────────────────────┐
 │ 7 golden_questions ── via ask client┼──────►│ llm-gateway (obs): LiteLLM proxy  │
 │ 8 land_llm_telemetry (gateway, lf)  │       │ aliases -> NVIDIA / OpenRouter /..│
 │ 9 record_run -> ops.run_log         │       │ budgets, spend log                │
 └─────────────────────────────────────┘       └──────┬────────────────────────────┘
                                                      │ traces, cost
                                               ┌──────▼────────────────────────────┐
                                               │ langfuse (obs): traces, scores,   │
                                               │ annotation queues, datasets       │
                                               └───────────────────────────────────┘
```

- **Laptop asleep at run time:** `catchup=True` plus a deterministic generator; missed days run
  in order at the next start.
- **Backfill (M7):** `make backfill FROM= TO=` runs one recorded DAG run per day, oldest first,
  with `airflow dags test`, and stops at the first failed day. Airflow's `backfill create` is not
  used: the scheduler starts no run of a paused DAG, and an unpaused DAG's catch-up runs would
  write the same DuckDB file beside the backfill. The DAG starts paused; unpausing it starts the
  daily schedule, which catches up from `WAREHOUSE_START_DATE` and skips days that already ran.
  The synthetic world must be contiguous from 2026-01-01 (orders refer to earlier customers).
- **load_lake:** `DELETE WHERE dt = ds` then `INSERT ... FROM read_parquet`. Idempotent.
- **dbt build:** `BashOperator` calling the dbt v2 binary.
- **publish_snapshot:** temp file, row counts verified, atomic rename, last 7 kept; only
  `data_warehouse_layer` and `data_mart_layer` reach `data/serve/analytics.duckdb`, comments
  included (M9).
- **refresh_ontology:** restart `auto-ontology` and `ingestion-service` through a socket proxy
  that allows exactly those two restarts (both hold the old file open until then). On start the
  ingestion service ingests the new file and runs one semantic compile pass, which compiles only
  what is new (M0), so the task waits for that pass instead of triggering another. The compile
  flag `semantic_compilation_enabled` lives in `frontend.configurations`; the `ao-seed` service
  sets it after the frontend migration. Skipped when the ontology profile is down (M9).
- **Auto Ontology's way out (M9):** its containers are only on an internal Docker network with
  no route to the internet; the gateway is on that network too, so it is the one way to a
  model. An nginx on both networks publishes the web UI on 127.0.0.1:3000. The backend port is
  never published: it answers without authentication because it trusts the frontend.
- **Resources:** about 8 GB for core plus ontology; the obs profile adds about 3.2 GiB
  (Langfuse 2.5, LiteLLM 0.65; measured in M0). Auto Ontology's backend, ingestion service and
  Postgres took 0.8 GiB. `make up-core`, `make up-ontology`, `make up-obs`.

## 7. Traceability, history and knowledge

| Question | Mechanism | Where |
|---|---|---|
| **Where did this row come from?** | Audit columns on every lake row: `_dt`, `_source_file`, `_loaded_at`, `_batch_id`. Warehouse rows add `_dbt_invocation_id`, `_dbt_updated_at` | In the tables |
| **Where did this number come from?** | dbt lineage to column level; every `rpt` model lists its upstream facts; every answer carries its SQL, snapshot id and trace id | `dbt docs`, archived artifacts, Langfuse |
| **Which model calls produced this answer, and what did they cost?** | Gateway records each call with alias, provider, model, tokens, cost, latency and job tag; Langfuse groups calls into the answer's trace | Langfuse, `fact__ops__llm_call` |
| **Was the answer right?** | Automatic check against reference SQL, plus a human label with reason and correction | Langfuse scores, `fact__ops__answer_label` |
| **What happened on this day?** | `ops.run_log` (date, git SHA, dbt invocation id, row counts per layer, test results, snapshot hash, model spend) and `ops.table_stats` | `ops` schema, `data/artifacts/<ds>/`, `docs/runs/<ds>.md` |
| **What was true before?** | Lake append-only and immutable per `dt`; dimensions keep history (`valid_from`, `valid_to`, `is_current`); last 7 snapshots kept; gateway config versioned in git | `lake`, `dim__*`, `data/serve/`, git |
| **Why is it built this way?** | One worknote per issue; one decision record per design choice; each rule keeps its reason and date | `docs/task-management/`, `docs/decisions/`, `.agents/rules/history/` |
| **What have we learned?** | The distilled knowledge base | `.agents/knowledge/` |

### Distilled knowledge

One lesson per file, with frontmatter (`id`, `title`, `tags`, `paths`, `status`, `created`,
`last_verified`, `evidence`, `supersedes`). Two kinds:

- **Engineering (`de-NNNN`)**: rule, why, how to apply, example.
- **Data (`da-NNNN`)**: what a column's values mean, with counts, the terms people use for them,
  and data-quality notes. Human labels feed this kind (section 8).

Generated and checked in CI, never hand-edited: `docs/engineering-distilled-knowledge.md`,
`docs/data-distilled-knowledge.md`, and `.agents/knowledge/index/` for `kb search`.
Lifecycle: expiry lint, evidence must resolve, retrieval test in CI, and every finished issue
either adds an entry or states "no new lesson".

## 8. LLM observability and human-in-the-loop

### 8.1 Every call goes through the gateway

Auto Ontology's four roles point at the gateway, and the gateway maps each alias to a provider:

```yaml
# infra/llm-gateway/config.yaml (versioned; secrets come from .env)
model_list:
  - model_name: openai/adw-reasoning        # what Auto Ontology asks for
    litellm_params: { model: openrouter/<model-id>,  api_key: os.environ/OPENROUTER_API_KEY }
  - model_name: openai/adw-non-reasoning
    litellm_params: { model: nvidia_nim/<model-id>,  api_key: os.environ/NVIDIA_API_KEY }
  - model_name: adw-embed                   # fixed; changing it forces a re-ingest
    litellm_params: { model: nvidia_nim/nvidia/nemotron-3-embed-1b, api_key: os.environ/NVIDIA_API_KEY }
general_settings:
  pass_through_endpoints:                   # rerank: LiteLLM's /rerank sends top_k, NVIDIA rejects it (M0)
    - path: /nvidia/rerank/reranking
      target: https://ai.api.nvidia.com/v1/retrieval/nvidia/<rerank-id>/reranking
      headers: { Authorization: bearer os.environ/NVIDIA_API_KEY }
```

```dotenv
# infra/auto-ontology/.env (excerpt)
REASONING_ENDPOINT=http://llm-gateway:4000/v1
REASONING_MODEL=openai/adw-reasoning
REASONING_API_KEY=<gateway virtual key for auto-ontology>
RERANK_ENDPOINT=http://llm-gateway:4000/nvidia/rerank/reranking   # ends in /reranking: native payload
```

- **Swapping provider** (for example to a new OpenRouter key or model) is one edit to
  `config.yaml` plus a gateway restart. Auto Ontology is untouched.
- **The embedding alias stays fixed.** Changing it means a full re-ingest and is its own issue.
- **One virtual key per caller** (`auto-ontology`, `golden-runner`, `agent-dev`), each with a
  daily budget. A caller over budget gets an error, not a surprise bill.
- **Every call is tagged** with caller and job (`ingest`, `compile`, `chat`, `golden`) so spend
  splits by purpose.
- **Recorded per call:** alias, provider, model, input tokens, output tokens, reasoning tokens
  when the provider reports them, cached tokens, cost in USD, latency, status, error.
  **Rerank and virtual keys (M8, decided in M9):** in LiteLLM OSS only the master key may call a
  pass-through route; a virtual key gets 403, and the per-key `allowed_passthrough_routes` is
  Enterprise-only. The rerank route therefore takes no key; it is reachable only on the private
  networks and 127.0.0.1, and the gateway still logs and traces each call, without a caller.
  **NVIDIA prices (M9):** LiteLLM has no price for the Nemotron model on NVIDIA and would log $0,
  so budgets would never trip; the NVIDIA aliases carry the OpenRouter list price of the same
  model as an estimate. **`openai/adw-non-reasoning`** turns the model's reasoning off
  (`chat_template_kwargs.enable_thinking: false`); before M9 both aliases reasoned.
  Exception: calls on a pass-through route (today only rerank) are logged and traced with model,
  latency, status and call id, but LiteLLM records no tokens and no cost for them (measured in
  M0). The telemetry mart reports them as a call count with an estimated cost (calls times the
  average tokens per rerank call measured at compile, at list price), labeled as estimated.
- **Reasoning content** is stored only when the provider returns it and only locally. With
  synthetic data this is safe; before any real data, decide what may leave the machine.

### 8.2 Traces that a person can read

| Trace level | Created by | Contains |
|---|---|---|
| Model call | Gateway | Prompt, completion, tokens, cost, latency |
| Answer | `ask` client (our code) calling the Auto Ontology chat API | Question, answer, SQL, rows, step trace (`thoughts`), snapshot id, conversation id, total cost |
| Run | Airflow | One trace per DAG run linking golden-question answers and the compile step |

Linking model calls to their answer: M0 found that Auto Ontology cannot forward a request id or
header to its model client (one answer showed up as 22 unrelated traces). Calls are attached by
caller key and time window, with golden questions asked one at a time, and the UI says so. A
small overlay patch that passes a per-request id in `_build_client`, `embed_texts` and `_scores`
is the next step if the window is too coarse.

Questions asked in the Auto Ontology web UI are still counted and costed by the gateway, but only
questions asked through the `ask` client (CLI, golden runner, review app) get a full answer trace.

### 8.3 Is the answer right? Two checks

1. **Automatic, every run.** A golden set of questions, each with reference SQL written by a
   person. The runner asks Auto Ontology, runs the reference SQL on the same snapshot, and scores
   `exact_match`, `within_tolerance`, `wrong`, `refused`. A `wrong` fails the DAG task.
2. **Human, on a sample and on every disagreement.** Answers go into a Langfuse annotation queue:
   - every golden answer scored `wrong` or `refused`;
   - every answer whose own SQL, re-run on the snapshot, does not reproduce the stated number;
   - a daily random sample of other `ask` answers (default 5).

Label schema (one form, the same for every answer):

| Field | Values |
|---|---|
| verdict | `correct`, `wrong_number`, `wrong_definition`, `wrong_grain`, `wrong_filter`, `should_have_refused`, `refused_wrongly` |
| reasoning_ok | `yes`, `partly`, `no`: did the step trace pick the right terms and joins |
| correct_answer | the right number or text, when known |
| correct_sql | the right SQL, when known |
| note | free text: which term was misread, which column was missed |

As built in M10: golden questions are `evals/golden/g-NNNN-*.yaml` (`check_golden` in CI);
`refused` means the answer has no rows with a number; a scalar answered with more than 20 rows is
`wrong`. Each question is asked once (no retry, so an unstable answer stays visible). The
answer's own SQL is re-run with file access off; the result is the score `sql_consistent`. Score
configs, the label form and the queue `answer-review` live in `infra/langfuse/scores.yaml`.
Task 7 and `record_run` do not depend on the previous day, so a wrong answer never holds the next
day's data; `make backfill` asks the golden set on its last day only.

### 8.4 What a label changes

```
label ──┬─► correct + reference SQL ─────► promoted into the golden set (dataset)
        ├─► wrong_definition / wrong_filter ─► da- knowledge entry (term -> column, literal)
        │                                     and a proposed ontology correction (reviewed)
        ├─► wrong_grain / wrong_number ──────► dbt issue: model, test or rpt table missing
        └─► every label ─────────────────────► data_lake_layer.langfuse__scores -> fact__ops__answer_label
```

- Ontology corrections go through Auto Ontology's own write path for certified definitions
  (checked in M0); nothing is written without a person approving it.
- Promotion to the golden set and new knowledge entries arrive as pull requests, so they pass the
  same checks as code.

### 8.5 The numbers that come out

Marts in the `ops` domain, queryable in SQL and in the Auto Ontology chat:

| Mart | Answers |
|---|---|
| `rpt__ops__llm_spend__daily` | cost and tokens by caller, job, alias, provider, model |
| `rpt__ops__llm_latency__daily` | p50 and p95 latency, error rate by alias |
| `rpt__ops__answer_quality__weekly` | accuracy on the golden set, human-label verdict mix, reasoning_ok share |
| `rpt__ops__provider_comparison__snapshot` | per provider and model: accuracy, cost per correct answer, latency, on the same golden set |
| `rpt__ops__pipeline_health__daily` | DAG duration, failed tasks, rows per layer, freshness |

### 8.6 Comparing providers before a swap

`make compare-providers ALIASES=nvidia-x,openrouter-y` runs the golden set once per candidate
alias, stores each run as a Langfuse experiment, and writes the comparison mart. A swap is
proposed only with that table in the pull request: accuracy, cost per correct answer, p95
latency, and the questions whose verdict changed.

### 8.7 Coding-agent usage

The coding agent's own token use is separate from the application's. Every pull request body
ends with an `## AI usage` section, rendered from the agent's local session logs. Routing the
coding agent through the gateway is a later option.

- **`.agents/ai-usage/model-pricing.yaml`**: list prices in USD per million tokens, per provider
  and model, keyed by the provider's API model id. Five rates per model (`input`,
  `cache_write_5m`, `cache_write_1h`, `cache_read`, `output`), plus optional `fast_multiplier`
  and `long_context` (threshold and a second rate set). Each provider block carries
  `source_url` (the official pricing page only) and `verified_on`; a block older than
  `stale_after_days` prints a warning.
- **`helpers/ai_usage_footer.py`**:
  - `render --body-file <pr-body>` reads the session logs (main agent and subagents, one count
    per message), prices each token class at its own rate, and replaces the `## AI usage`
    section at the end of the body.
  - The footer has one fixed shape: the `## AI usage` heading, then a fenced `text` block
    with these six lines, in this order, and after the block only the hidden ledger line
    (an HTML comment, see below):

    ```text
    Harness Tool: <name of harness>
    Model Name: <model id> (effort <level>)[, <model id> (effort <level>) ...]
    Input Token Usage: <tokens> ($<usd>) - Cache hit (<tokens>, $<usd>)
    Output Token Usage: <tokens> ($<usd>) - Cache hit (<tokens>, $<usd>)
    Total Token: <tokens> ($<usd>) - Cache hit (<tokens>, $<usd>)
    Metadata: <free text>
    ```

    - Input tokens are all input classes: uncached input, cache writes (5m and 1h) and cache
      reads, each priced at its own rate. Its cache hit is the cache-read tokens and their cost.
    - Output tokens are never cached, so the output cache hit is always `(0, $0.00)`; the slot
      stays so every footer has the same shape.
    - Total is input plus output; its cache hit equals the input cache hit.
    - Tokens are written with thousands separators, USD with two decimals.
    - Metadata carries the rest in one line: requests, cache writes by class, subagents, what
      each model was used for, the per-model split when there is more than one model, the
      pricing source and date, and the words "list-price estimate, not money paid".
  - It counts only tokens since the previous footer of the same session, recorded in the hidden
    ledger line, so totals across several PRs add up instead of repeating.
  - A harness without a log reader passes its token counts as flags.
  - `check-prices` validates the pricing file (every class present, numbers positive, dates
    valid).
- **No tool watermark.** The footer replaces lines such as "Generated with ..."; `check_pr_body`
  fails a PR body that has a watermark or lacks the footer.

## 9. Agent harness

```
AGENTS.md                 the map and the loop, under 200 lines, size checked in CI
CLAUDE.md                 one line: @AGENTS.md
.agents/
  harnesses.yaml          registry of wired agent tools and their six duties (Claude Code first)
  rules/  rules/history/  one line per rule; the story behind it on demand
  skills/                 issue-create, branch-name, pr-open, closeout, dbt-add-model,
                          run-backfill, ontology-refresh, knowledge-add, verify-literal,
                          analyst-explore, analyst-validate, analyst-sensemake,
                          label-review, provider-compare
  knowledge/              entries/{de,da}/, cold/, index/, evals/
  toolbelt.md             every CLI and server: owner, access, reason, review date
  ai-usage/model-pricing.yaml   list prices per token class, read by the PR footer
.agent-activity-logs/     gitignored; one JSONL file per session
.claude/                  settings (deny > ask > allow), three hooks
helpers/                  check_*.py, kb CLI, log_agent_action.py, closeout script
tests/governance/         pytest wrapper per checker
.github/workflows/ci.yml  blocking; branch protection requires green
```

**The loop** (numbered in `AGENTS.md`, one GitHub issue, one worktree, one worknote, one PR):

0. Pre-flight: is the previous issue closed out?
1. Plan in chat; wait for approval. No edits before this.
2. Worktree under `.worktrees/<issue>-<slug>/`, branch named from the issue.
3. Analyse from inside the worktree; surface scope changes.
4. Issue created or confirmed, labelled, moved to In Progress.
5. Work, plus the worknote and any knowledge entry, in the same commit.
6. Ask before commit and PR. PR body has the test plan with result tokens.
7. Close out only when told: merged and green, issue updated and closed, worktree removed.
   Merging is never implied.

**Five hard rules:** plan before edit; branch, never the default; never merge unless told to
merge a named PR; no secrets, home paths or personal identifiers in files; every number cites
its query.

**Skills, not entry-doc text:** the working roles (data engineer, analytics engineer, QA,
analyst) live as skills that load only when used. The analyst skills run three modes: explore
(schema, counts, nulls, freshness), validate (same metrics before and after, each delta labelled
expected, benign or suspect), sensemake (anchors, a frame, a stress test, actions; confidence out
of 10; fact, inference and hypothesis labelled).

**Verify a literal before filtering on it.** Before any `WHERE col = '<literal>'`, profile the
column (`GROUP BY col`) or cite a `da-` entry verified within 90 days. New profiles become `da-`
entries.

**Activity log:** at each decision point and external call the agent appends one JSON line
(session, role, action, tool, one-line args, one-line result, status) via
`helpers/log_agent_action.py`. Gitignored.

**Harness registry:** `harnesses.yaml` declares each wired tool against six duties (entry,
rules, skills, hooks, permissions, mcp). The parity checker derives what it checks from the
registry and fails on any undeclared duty. Rule mirrors per tool are generated only when a second
tool is wired.

Blocking checks from the first merge:

| Check | Enforces |
|---|---|
| `check_naming` | layer prefixes, `<domain>` vocabulary, cadence suffix, column naming |
| `check_bundle` | every model has yml, description, column descriptions and key tests |
| `check_layers` | allowed reads per layer |
| `check_audit_columns` | audit columns present on lake and warehouse tables |
| `check_entry_size` | `AGENTS.md` cap; size budget per rule file |
| `check_harness_parity` | every registered tool declares all six duties and reaches every skill |
| `check_knowledge` | frontmatter, expiry, evidence resolves, generated docs current, recall floor |
| `check_worknote` | PR touches a worknote for its issue |
| `check_pr_body` | pre-merge and post-merge sections; every pre-merge item ends in `→ PASS`, `→ FAIL: reason` or `→ SKIP[rule]: reason`; ends with the `## AI usage` footer in the fixed six-line shape (section 8.7); no tool watermark |
| `check_prices` | `model-pricing.yaml` is complete and valid; stale provider blocks warn, never block |
| `check_gateway_only` | no provider URL or provider key name outside `infra/llm-gateway/` and `.env.example` |
| `check_duckdb_compat` | loader, dbt driver and Auto Ontology pin open one file |
| `dbt build --target ci` | models and tests pass on a 3-day dataset |
| `gitleaks` + path check | no secrets, no home paths |

Data access ceiling: agents get `SELECT` on the serving snapshot through a read-only
connection; builds run in `dev` and `ci`; the daily build file is written only by Airflow.

## 10. Repository layout

```
project-agentic-data-warehouse/
  AGENTS.md  CLAUDE.md  README.md  Makefile  PLAN.md  .env.example
  .agents/  .claude/  .github/
  generator/            synthetic source (Python, uv) + reference files
  loader/               landing -> lake (business and platform sources)
  dbt/models/data_{lake,staging,warehouse,mart}_layer/<table>/   <table>.sql .yml .md
  airflow/              dags/, Dockerfile (Airflow + dbt binary + uv env)
  publish/              snapshot, ontology refresh, run recorder
  llm/                  ask client, golden runner, provider comparison, label export
  evals/golden/         questions with reference SQL (grown from labels)
  infra/compose.yml     profiles core | ontology | obs
  infra/auto-ontology/  UPSTREAM_SHA, compose.override.yml, .env.example, bootstrap.sh
  infra/llm-gateway/    config.yaml, budgets, virtual-key bootstrap
  infra/langfuse/       compose fragment, project bootstrap, annotation queue and score config
  helpers/  tests/
  docs/                 task-management/, decisions/, runs/, generated knowledge docs
  data/                 gitignored: landing/, build/, serve/, artifacts/
```

## 11. Milestones (one issue, one branch, one worknote, one PR each)

| # | Milestone | Done when |
|---|---|---|
| M0 | **Spike, throwaway.** dbt v2 on macOS arm64: bundled DuckDB version; seeds, incremental, snapshots, `persist_docs`, double-underscore names. File compatibility across loader, dbt, Auto Ontology. Auto Ontology ingests a DuckDB file, reads comments, picks up a replaced file after restart. Auto Ontology through LiteLLM with `openai/` aliases for chat, embed and `/rerank`. One OpenRouter chat model through the gateway. Request id or header passthrough. Langfuse and Phoenix memory on the laptop | A findings note answers each item with its command; D1, D2, D5 and D6 confirmed or changed |
| M1 | Repo skeleton and harness: `AGENTS.md` with the loop, registry, hooks, activity log, CI with entry-size, parity, secrets, worknote, PR-body and pricing checks, branch protection requiring green CI; `model-pricing.yaml` and `ai_usage_footer.py` with tests | A PR without a worknote, with an untokened pre-merge item, or without the AI usage footer fails CI; the footer on M1's own PR is rendered by the helper |
| M2 | Generator: seed, daily partitions, documented defects, unit tests | Same seed and date give identical files |
| M3 | Loader into `lake` with audit columns; `check_duckdb_compat` | Loading a day twice leaves counts unchanged |
| M4 | dbt project: staging, warehouse, mart, tests, docs, history on two dims | `dbt build --target ci` green in CI |
| M5 | Governance checkers (naming, bundle, layers, audit columns, gateway-only) blocking | A deliberately bad model fails each checker |
| M6 | Knowledge base: entry format, `kb` CLI, generated docs, lint, retrieval eval, first ten entries; verify-literal and analyst skills | A stale or unevidenced entry fails CI |
| M7 | Airflow compose (core profile) and `warehouse_daily` tasks 1 to 4 and 9; `ops.run_log`; backfill | A 7-day backfill succeeds from a clean checkout with `make up-core` |
| M8 | LLM gateway and Langfuse (obs profile): aliases, virtual keys, budgets, job tags, traces | A test call shows up in Langfuse with tokens and cost; a caller over budget is refused |
| M9 | Publish snapshot, Auto Ontology overlay at pinned SHA wired to the gateway, refresh task | Chat answers a revenue question and every model call it made is in the gateway log |
| M10 | `ask` client and golden runner: answer traces, automatic scores, DAG task 7 | A wrong golden answer fails the task and appears in the annotation queue |
| M11 | Human-in-the-loop: label form, queue rules, label export (task 8), `ops` marts, label-to-golden and label-to-knowledge pull requests | A labeled `wrong_definition` produces a `da-` entry PR; the quality mart shows the label |
| M12 | Provider comparison: `make compare-providers`, comparison mart, a first NVIDIA vs OpenRouter run; local runbook | The comparison table is in a PR; a fresh clone reaches a working chat from the runbook alone |
| Later | Olist domain; hosting; a second agent tool with generated rule mirrors; coding agent through the gateway; agent merge for docs-only PRs | Separate issues |

Order: M0, M1, then M2 to M5 in sequence. M6 beside M4 and M5. M7 needs M4. M8 can start after
M1 and must finish before M9, so the first ingest already runs through the gateway. M10 needs M9.
M11 needs M10. M12 last.

## 12. Keeping a later move cheap

- Everything runs from Compose with relative paths and `.env`; nothing assumes macOS.
- Images built for both arm64 and amd64.
- State to carry: `data/landing/`, the Auto Ontology Postgres dump, the Langfuse databases (or
  their export), `.env`. The warehouse file is rebuildable from landing.
- On a server, change only bind addresses, a reverse proxy with TLS, and backups. Ports 3001,
  3002, 5432, 5050 and the gateway port stay unpublished in both setups.

## 13. Risks

| Risk | Mitigation |
|---|---|
| dbt v2 DuckDB adapter lacks a feature the design assumes | M0: seeds, incremental, snapshots, `persist_docs` and double-underscore names all pass on 2.0.12; fallback stays `dbt-duckdb` on dbt Core 1.x |
| Auto Ontology on DuckDB is less exercised than on Postgres | M0 ingests a real file; fallback is publishing to Postgres |
| Auto Ontology's NVIDIA-specific client paths break through the gateway | `openai/` alias names; M0 tests all four roles. A role that still fails is routed through a gateway pass-through route that forwards the provider's native API unchanged, so its calls are still counted and traced; they are not costed by the gateway and get the estimated cost described in section 8.1. Never a direct provider URL: that would break the gateway-only invariant and `check_gateway_only` |
| Model calls cannot be linked to their answer | Confirmed in M0. Time-window linking, stated in the UI; overlay patch or upstream request for a header hook |
| Auto Ontology ignores DuckDB column comments, so dbt docs never reach it | Confirmed in M0. **Mitigated in M9** by the overlay patch `infra/auto-ontology/patches/0001-duckdb-connector-reads-comments.patch` (table and column comments into the catalog's `description`); worth offering upstream |
| Rerank through LiteLLM's `/rerank` fails for NVIDIA (`top_k` rejected) | Pass-through route (section 8.1); rerank calls are then counted and traced but not costed by the gateway, so their cost is an estimate (section 8.1). A small share, since rerank runs only for bridge tables at compile. If it grows, a LiteLLM custom handler that reads `usage.prompt_tokens` from NVIDIA's response gives an exact cost |
| An NVIDIA model is overloaded (M0: `nemotron-3.5-embed-1b` returned 503 all day) | Embedding alias on `nemotron-3-embed-1b`, served by NVIDIA and OpenRouter with identical vectors, so a fallback needs no re-ingest |
| Laptop memory with all profiles up | Compose profiles; M0 measured about 4 GiB for ontology plus obs, so Langfuse stays; Phoenix if Airflow pushes the VM over |
| Labels never get done | Queue capped at a small daily sample; golden-set failures always queued; the weekly quality mart shows unlabeled counts |
| A provider swap changes accuracy silently | A swap PR must carry the comparison table; golden runner runs daily |
| Sending data to an external provider | Synthetic data in v1; a data-egress decision record before any real data |
| Three DuckDB builds drift apart | `check_duckdb_compat` in CI |
| Knowledge base rots | Expiry lint, evidence check and retrieval eval are blocking |

## 14. Left to the implementer

Exact version pins (resolved at M0, written to `toolbelt.md`), generator volumes and
distributions, column lists, checker error codes, wording of rules, the first golden questions.
Names (aliases, keys, labels), owners, budget numbers, the recall floor, the daily review sample
size and the list of blocking checks stay with the owner.
