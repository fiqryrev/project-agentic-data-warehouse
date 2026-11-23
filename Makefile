# Local shortcuts. Every target runs through uv, so the locked versions are used.
START ?= 2026-01-01
END   ?= 2026-01-07
SEED  ?= 42
LANDING ?= data/landing
# Manual loads and dbt-build use the development file; only Airflow writes data/build/ (AGENTS.md, Data access).
DB    ?= data/dev/dwh.duckdb

.PHONY: test checks generate load dbt-build dbt-ci env-secrets up-core down-core backfill run-log up-obs down-obs llm-smoke down up-ontology down-ontology ontology-check ask golden label-prs compare-providers

test:
	uv run pytest -q

checks:
	uv run python -m helpers.check_entry_size
	uv run python -m helpers.check_harness_parity
	uv run python -m helpers.check_secrets
	uv run python -m helpers.check_prices
	uv run python -m helpers.check_duckdb_compat
	uv run python -m helpers.check_naming
	uv run python -m helpers.check_bundle
	uv run python -m helpers.check_layers
	uv run python -m helpers.check_audit_columns
	uv run python -m helpers.check_gateway_only
	uv run python -m helpers.check_knowledge
	uv run python -m helpers.check_golden

generate:
	uv run python -m generator --start $(START) --end $(END) --seed $(SEED) --out $(LANDING)

load:
	uv run python -m loader --start $(START) --end $(END) --landing $(LANDING) --db $(DB)
	uv run python -m llm.telemetry --db $(DB) --init-only

dbt-build:
	cd dbt && uv run --group dbt dbt build --profiles-dir . --target dev

# The same 3-day build CI runs, in data/ci/.
dbt-ci:
	rm -rf data/ci
	uv run python -m generator --start 2026-01-01 --end 2026-01-03 --out data/ci/landing
	uv run python -m loader --start 2026-01-01 --end 2026-01-03 --landing data/ci/landing --db data/ci/dwh.duckdb
	uv run python -m llm.telemetry --db data/ci/dwh.duckdb --init-only
	cd dbt && uv run --group dbt dbt build --profiles-dir . --target ci

# --- Local stack (infra/compose.yml). Airflow UI: http://127.0.0.1:8080 ---
COMPOSE = docker compose -f infra/compose.yml --env-file .env --profile core
FROM ?= $(START)
TO   ?= $(END)

# .env is gitignored: created from .env.example, empty secrets filled with random values.
env-secrets:
	uv run python airflow/env_secrets.py .env .env.example

up-core: env-secrets
	GIT_SHA=$$(git rev-parse HEAD) $(COMPOSE) up -d --build --wait

# down-<profile> removes only that profile's containers: the shared network "wh" stays for the
# other profile (compose `down` would try to remove it while still in use). Named volumes stay.
down-core:
	$(COMPOSE) rm --stop --force

# Every profile down, then the network.
down:
	docker compose -f infra/compose.yml --env-file .env --profile core --profile obs --profile ontology down

# Backfill FROM..TO through the scheduler (one day at a time, oldest first) and wait for it.
backfill:
	$(COMPOSE) exec airflow-scheduler bash /opt/wh/airflow/backfill.sh $(FROM) $(TO)

# Gateway (http://127.0.0.1:4000) and Langfuse (http://127.0.0.1:3001, login admin@example.com,
# password LANGFUSE_ADMIN_SECRET in .env). Creates the per-caller virtual keys (budgets.yaml).
OBS = docker compose -f infra/compose.yml --env-file .env --profile obs

up-obs: env-secrets
	uv run python infra/llm-gateway/bootstrap.py check-keys
	$(OBS) up -d --wait
	uv run python infra/llm-gateway/bootstrap.py keys
	uv run python infra/langfuse/bootstrap.py

down-obs:
	$(OBS) rm --stop --force

# One tagged call that must reach Langfuse with tokens and cost; one caller refused over budget.
llm-smoke:
	uv run python -m llm.gateway_smoke

# Auto Ontology at infra/auto-ontology/UPSTREAM_SHA plus our patches: UI http://localhost:3000
# (login admin@example.com, password AO_ADMIN_SECRET in .env); scripts use its /api routes.
# Needs `make up-obs` first: its only way to a model is the gateway, with the auto-ontology key.
ONT = docker compose -f infra/compose.yml --env-file .env --profile ontology

up-ontology: env-secrets
	@grep -q '^GATEWAY_KEY_AUTO_ONTOLOGY=.' .env || (echo "run make up-obs first (it writes GATEWAY_KEY_AUTO_ONTOLOGY)"; exit 1)
	bash infra/auto-ontology/bootstrap.sh
	$(ONT) up -d --build --wait

down-ontology:
	$(ONT) rm --stop --force

# Publish the build file, refresh Auto Ontology, ask a revenue question, check the answer against
# SQL on the snapshot and every model call against the gateway's log.
DAY ?= 2026-01-05
ontology-check:
	uv run python -m llm.ontology_check --day $(DAY)

# One question to Auto Ontology with a full answer trace in Langfuse (llm/ask.py).
ask:
	uv run python -m llm.ask "$(Q)"

# Every golden question, scored against reference SQL on the snapshot (llm/golden.py, DAG task 7).
DS ?= $(shell date -u +%F)
golden:
	uv run python -m llm.golden --ds $(DS)

# New human labels from the Langfuse queue into golden questions, da- entries and dbt issues
# (llm/labels.py; skill label-review). Dry run unless OPEN=1.
label-prs:
	uv run python -m llm.labels $(if $(OPEN),--open,) $(if $(BASE),--base $(BASE),)

# The golden set once per candidate provider; report in data/runs/ (gitignored; llm/compare.py, PLAN 8.6).
ALIASES ?= nvidia,openrouter
compare-providers:
	uv run python -m llm.compare --aliases $(ALIASES)

# The run log of the daily build file, read-only.
run-log:
	uv run python -m publish.show_run_log data/build/dwh.duckdb
