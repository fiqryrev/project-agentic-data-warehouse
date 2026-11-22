# Local shortcuts. Every target runs through uv, so the locked versions are used.
START ?= 2026-01-01
END   ?= 2026-01-07
SEED  ?= 42
LANDING ?= data/landing
# Manual loads and dbt-build use the development file; only Airflow writes data/build/ (AGENTS.md, Data access).
DB    ?= data/dev/dwh.duckdb

.PHONY: test checks generate load dbt-build dbt-ci

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

generate:
	uv run python -m generator --start $(START) --end $(END) --seed $(SEED) --out $(LANDING)

load:
	uv run python -m loader --start $(START) --end $(END) --landing $(LANDING) --db $(DB)

dbt-build:
	cd dbt && uv run --group dbt dbt build --profiles-dir . --target dev

# The same 3-day build CI runs, in data/ci/.
dbt-ci:
	rm -rf data/ci
	uv run python -m generator --start 2026-01-01 --end 2026-01-03 --out data/ci/landing
	uv run python -m loader --start 2026-01-01 --end 2026-01-03 --landing data/ci/landing --db data/ci/dwh.duckdb
	cd dbt && uv run --group dbt dbt build --profiles-dir . --target ci
