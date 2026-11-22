# 20: M8 LLM gateway and Langfuse (obs profile): aliases, virtual keys, budgets, job tags, traces

## Goal

PLAN section 11, row M8 (design in sections 8.1 and 8.2): every model call goes through a LiteLLM
gateway that records, limits and traces it in Langfuse. Done when a test call shows up in
Langfuse with tokens and cost, and a caller over budget is refused.

## Plan (as approved)

Approved in chat on 2026-11-22, including a few cheap real model calls on the owner's keys.

1. `infra/compose.yml`, profile obs: LiteLLM 1.110.2 (127.0.0.1:4000), Langfuse 4.83.0 web and
   worker (127.0.0.1:3001), ClickHouse, Redis, MinIO, one Postgres with two databases; Langfuse
   telemetry off, headless init of org, project, keys and UI login.
2. `infra/llm-gateway/config.yaml` with the M0 aliases and the rerank pass-through,
   `langfuse_otel` callback; `budgets.yaml` and `bootstrap.py` for one virtual key per caller.
3. `make up-obs`, `make down-obs`, `make llm-smoke`; secrets generated into `.env`.
4. Static tests for config, budgets, compose and the smoke helpers.

## Decisions

- **Versions and digests from M0** (`docs/m0-findings.md`, "Version pins found"); every obs image
  is pinned by digest, and the digests resolved today match M0's. Redis is `7.4.7` (M0 used
  the floating `redis:7`). Langfuse publishes on 3001 because 3000 is Auto Ontology's (M9).
- **One Postgres for the profile**, databases `litellm` and `langfuse` (`infra/obs-db/init.sql`):
  one container less than two Postgres, 43 MiB.
- **Secrets:** every password and key is a `*_SECRET` in `.env`, filled with random hex by
  `make up-obs` (`airflow/env_secrets.py`, now shared by both profiles). Prefixes the tools need
  are added in compose (`sk-` for the LiteLLM master key, `pk-lf-`/`sk-lf-` for Langfuse). The
  UI login is `admin@example.com` with `LANGFUSE_ADMIN_SECRET`.
- **Provider keys are optional in compose, required by `make up-obs`.** Compose interpolates every
  variable of every profile, so a required provider key (`:?`) would stop `make up-core` for someone with
  no provider key; `bootstrap.py check-keys` stops `make up-obs` instead.
- **The gateway's environment lives in `infra/llm-gateway/service.yml`**, merged with `extends`.
  `check_gateway_only` flagged the provider key names in `infra/compose.yml`; exempting the whole
  compose file would let any later service receive a provider key, so the names moved into the
  folder that is already exempt.
- **Callers and budgets** (`budgets.yaml`, per day, USD at list price): `auto-ontology` 2.00,
  `golden-runner` 1.00, `agent-dev` 0.50, each limited to the aliases it needs and tagged
  `caller:<name>` in the key metadata. Jobs tag their calls (`metadata.tags`, for example
  `job:smoke`); Langfuse shows both tags on the trace. `bootstrap.py keys` updates a working key
  in place and creates a missing one, so it runs on every `make up-obs`.
- **Budget refusal is HTTP 422 `budget_exceeded`** in LiteLLM 1.110.2, not 400 or 429 (seen on
  the first smoke run); the smoke test matches the error type. Its message names the key alias
  and the last four characters of the key, so the smoke test prints only the cost and budget.
- **Langfuse read path:** `/api/public/v2/observations?type=GENERATION&fields=core,basic,usage,metadata,model`;
  the call is matched on the provider's response id (`attributes.llm.response.id`). Ingestion took
  under 10 seconds.
- **Rerank needs the master key in LiteLLM OSS (new finding).** A virtual key gets 403 on the
  pass-through route, and `allowed_passthrough_routes` on a key is Enterprise-only (403 from
  `/key/generate`); a key without a model restriction is refused too. M0 had tested the route with
  the master key. The route stays `auth: true` (master key only) and M9 decides how Auto Ontology
  reaches rerank without the master key. PLAN section 8.1 notes it.

## Done

- `make up-obs` on fresh volumes: all seven containers healthy; Langfuse org, project, keys and
  login created headless; `bootstrap.py keys` created the three keys, and a second run updated
  them in place.
- `make llm-smoke` -> `PASS`:
  - call: `openai/adw-or-chat` through the `agent-dev` key, tagged `job:smoke`, HTTP 200;
  - trace: the Langfuse generation with 24 input and 3 output tokens, $0.00000192, caller
    `agent-dev`, tags `job:smoke` and `caller:agent-dev` (the gateway reported the same cost);
  - budget: a temporary key with a $0.000001 budget answered once, then
    `HTTP 422 budget_exceeded; Current cost: 2.568e-05, Max budget: 1e-06`; the key was deleted.
- Extra checks through the gateway: `adw-embed` returned 2048 dimensions; rerank without a key
  401, with a virtual key 403, with the master key 200 (see Decisions).
- Real model spend for all of M8's probes and smoke runs: under $0.001 at list price (each call
  between $0.000002 and $0.00005, from `x-litellm-response-cost`).
- Memory with obs up (`docker stats`): about 4.9 GiB (ClickHouse 2.09, LiteLLM 1.04, langfuse-web
  0.90, langfuse-worker 0.58, MinIO 0.22, Postgres 0.04, Redis 0.01), more than M0's 3.2 GiB.
- `uv run pytest -q` -> 271 passed (13 new in `tests/pipeline/test_llm_gateway.py`); `make checks`
  -> all eleven OK, `check_gateway_only` included.

## Open

- **Memory before M9:** obs measured 4.9 GiB, core 0.9 GiB; Auto Ontology needs about 0.8 GiB
  more on a 7.75 GiB VM. Options: cap ClickHouse's memory (`max_server_memory_usage`), or run
  core and obs at different times. Decide in M9.
- Rerank access for Auto Ontology without the master key (M9).
- Landing the gateway spend log and Langfuse traces in the lake (DAG task 8, M11).
