# Runbook: from a fresh clone to a working chat

Everything runs on one laptop with Docker. Ports are bound to 127.0.0.1. The commands are run from
the repository root. The design is in [PLAN.md](../PLAN.md), the work loop in
[AGENTS.md](../AGENTS.md).

## 1. Prerequisites

- macOS or Linux with Docker Desktop (or Docker Engine and Compose v2), the VM given at least
  7.75 GiB of memory: the three profiles together take about 6 GiB.
- [uv](https://docs.astral.sh/uv/) and git. uv installs the pinned Python and every package.
- An API key for each model provider named in the provider section of `.env.example`. Every
  model call goes through the gateway; the keys live only in `.env`.

## 2. Clone and configure

```bash
git clone https://github.com/fiqryrev/project-agentic-data-warehouse.git
cd project-agentic-data-warehouse
uv sync
uv run python airflow/env_secrets.py .env .env.example
```

The last line creates `.env` from `.env.example` with every `*_SECRET` filled (each `make up-*`
does the same and keeps what is set). Open `.env` and fill the provider keys (the `--- obs profile` section). Never commit `.env`.

**Volumes are shared by name.** The compose project is always `wh`, so a second checkout on the
same machine uses the same volumes (Airflow history, gateway keys, Langfuse, Auto Ontology's
catalog). Their passwords are set when a volume is first created: on a machine that already ran
the stack, copy that checkout's `.env` instead of starting from `.env.example`, or new secrets
will not match the volumes. To start truly clean instead, `make down` then
`docker volume ls -q --filter name=wh_ | xargs docker volume rm` deletes all that state.

## 3. Build eight days of the warehouse (core profile)

```bash
make up-core
make backfill FROM=2026-01-01 TO=2026-01-08
```

`make up-core` builds the Airflow image and starts Airflow (UI at http://127.0.0.1:8080).
The backfill runs DAG `warehouse_daily` once per day, oldest first, and stops at the first failed
day; each day ends with a `[record_run] <day>: passed` line. The world must start at 2026-01-01.
Without the other profiles, the ontology refresh, golden questions and telemetry landing report
`skipped`, which is expected. Check the run log:

```bash
make run-log
```

## 4. Gateway and traces (obs profile)

```bash
make up-obs
make llm-smoke
```

`make up-obs` checks the provider keys, starts LiteLLM (http://127.0.0.1:4000) and Langfuse
(http://127.0.0.1:3001, login `admin@example.com`, password `LANGFUSE_ADMIN_SECRET` in `.env`),
creates one virtual key per caller with its daily budget (`infra/llm-gateway/budgets.yaml`), and
the score configs and annotation queue `answer-review`. `make llm-smoke` must print `PASS`: one
call reached Langfuse with tokens and cost, and a caller over its budget was refused.

## 5. Auto Ontology (ontology profile)

```bash
make up-ontology
make ontology-check
```

`make up-ontology` clones Auto Ontology at the pinned commit into a gitignored folder, applies
the overlay patch, builds the images and starts them on the published snapshot
`data/serve/analytics.duckdb`. The first start ingests the snapshot and compiles its semantic
layer: about 9 minutes and a few cents of model calls. `make ontology-check` waits for that
compile, asks a revenue question, compares the answer with SQL on the snapshot, matches every
model call in the gateway log and Langfuse, and proves the containers have no other way out. It
must print `PASS`. The chat UI is http://localhost:3000 (use `localhost`, not 127.0.0.1), login
`admin@example.com` with `AO_ADMIN_SECRET` from `.env`.

## 6. Daily use

| Command | What it does |
|---|---|
| `make ask Q="..."` | one question with a full answer trace in Langfuse |
| `make golden DS=<day>` | the golden set, scored against reference SQL (DAG task 7 does this daily) |
| `make backfill FROM=<d> TO=<d>` | more days; golden questions are asked on the last one only |
| `make label-prs` / `OPEN=1` | labels from the Langfuse queue into golden questions, `da-` entries, dbt issues (skill `label-review`) |
| `make compare-providers ALIASES=nvidia,openrouter` | the golden set once per provider; report in `docs/runs/` |
| `make dbt-ci` | the 3-day build CI runs |
| `make test`, `make checks` | the tests and the governance checkers CI runs |

Unpausing `warehouse_daily` in the Airflow UI starts the daily schedule; it catches up from
`WAREHOUSE_START_DATE` and skips days that already ran.

## 7. Stop

```bash
make down
```

stops every profile and removes the network; named volumes and `data/` stay. `make down-core`,
`make down-obs` and `make down-ontology` stop one profile.

## 8. When something is off

| Symptom | Cause and fix |
|---|---|
| A Postgres container restarts with "password authentication failed" | `.env` secrets differ from an existing volume (section 2): use the `.env` that created it |
| Langfuse reads fail with "memory limit exceeded" | ClickHouse needs its 3 GiB ceiling; give the Docker VM more memory |
| Sign-in to the chat answers "Invalid origin" | open http://localhost:3000, not 127.0.0.1 |
| `make ontology-check` fails once on the answer | the chat now and then ends without SQL; it retries once, run it again |
| The gateway refuses a call with `budget_exceeded` | the caller spent its daily budget (`budgets.yaml`); wait for the reset or raise it in a PR |
| Golden questions come back `refused` | expected for some questions on every run (M10); they go to the queue for a person |
| Task 8 or 6 `skipped` | the obs or ontology profile is down, which is allowed |
