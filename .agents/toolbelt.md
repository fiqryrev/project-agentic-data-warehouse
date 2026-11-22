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
| gitleaks | owner | CI only | secret scan beside `check_secrets` | 2027-02-21 |

Planned (added with their milestone): LiteLLM gateway and Langfuse (M8), Auto Ontology (M9). Their verified version pins are
in `docs/m0-findings.md` ("Version pins found").
