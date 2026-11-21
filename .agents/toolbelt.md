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
| `make` | owner | run | shortcuts in `Makefile` | 2027-02-22 |
| gitleaks | owner | CI only | secret scan beside `check_secrets` | 2027-02-21 |

Planned (added with their milestone): `dbt` (M4), Docker compose and Airflow
(M7), LiteLLM gateway and Langfuse (M8), Auto Ontology (M9). Their verified version pins are
in `docs/m0-findings.md` ("Version pins found").
