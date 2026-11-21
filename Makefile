# Local shortcuts. Every target runs through uv, so the locked versions are used.
START ?= 2026-01-01
END   ?= 2026-01-07
SEED  ?= 42
LANDING ?= data/landing
DB    ?= data/build/warehouse.duckdb

.PHONY: test checks generate load

test:
	uv run pytest -q

checks:
	uv run python -m helpers.check_entry_size
	uv run python -m helpers.check_harness_parity
	uv run python -m helpers.check_secrets
	uv run python -m helpers.check_prices
	uv run python -m helpers.check_duckdb_compat

generate:
	uv run python -m generator --start $(START) --end $(END) --seed $(SEED) --out $(LANDING)

load:
	uv run python -m loader --start $(START) --end $(END) --landing $(LANDING) --db $(DB)
