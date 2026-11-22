# Toolbelt

Every CLI and server an agent may use. Review each line by its date; remove what is unused.

| Tool | Owner | Access | Reason | Review by |
|---|---|---|---|---|
| `git` | owner | read; commit and push under `ask` | version control, worktrees | 2027-02-21 |
| `gh` | owner | read; issue and PR writes under `ask`; `gh pr merge` denied | issues, PRs, CI status | 2027-02-21 |
| `uv` | owner | run | Python env, tests, helpers | 2027-02-21 |
| `pytest` | owner | run | governance tests in `tests/governance/` | 2027-02-21 |
| `python3` | owner | run | hooks and helpers (standard library for hooks) | 2027-02-21 |
| GitHub Actions | owner | CI only | blocking checks in `.github/workflows/ci.yml` | 2027-02-21 |
| `duckdb` (Python) | owner | run; agents read the serving snapshot read-only (M9) | loader writes `lake`; pins in `infra/duckdb-pins.yaml` | 2027-02-22 |
| `dbt` 2.0.12 | owner | run `dev` and `ci` targets; `prod` is Airflow's | builds staging, warehouse, mart (`dbt/`) | 2027-02-22 |
| `kb` (`helpers/kb.py`) | owner | run; writes only `.agents/knowledge/` and the generated docs | search, add and render knowledge entries | 2027-02-22 |
| `make` | owner | run | shortcuts in `Makefile` | 2027-02-22 |
| Docker compose | owner | run `make up-core`, `make down-core`, `make backfill`; agents never `down -v` | local stack in `infra/compose.yml` (profile core) | 2027-02-22 |
| Airflow 3.3.2 | owner | UI on 127.0.0.1:8080; CLI inside the scheduler container | runs `warehouse_daily`, the only writer of `data/build/` | 2027-02-22 |
| LiteLLM 1.110.2 | owner | gateway on 127.0.0.1:4000; agents call it with their own virtual key, never the master key | every model call, budgets, spend log (`infra/llm-gateway/`) | 2027-02-22 |
| Langfuse 4.83.0 | owner | UI on 127.0.0.1:3001; read API with the project keys in `.env` | traces, tokens and cost per call | 2027-02-22 |
| Auto Ontology (`f3c310c7a279` + overlay patches) | owner | UI on 127.0.0.1:3000 with the admin login in `.env`; agents read answers, never the backend port | ontology, text-to-SQL chat over the snapshot (`infra/auto-ontology/`) | 2027-02-22 |
| gitleaks | owner | CI only | secret scan beside `check_secrets` | 2027-02-21 |

Version pins verified in M0 are in `docs/m0-findings.md` ("Version pins found").
