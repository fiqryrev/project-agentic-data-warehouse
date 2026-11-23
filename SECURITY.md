# Security policy

## What this is

A showcase that runs on one laptop: DuckDB, dbt, Airflow, NVIDIA Auto Ontology, a LiteLLM gateway
and Langfuse in Docker compose (`infra/compose.yml`). It is not a hosted service and has no
releases; the supported version is the `main` branch.

## Reporting a vulnerability

Use GitHub's private vulnerability reporting: the **Security** tab of this repository, then
**Report a vulnerability**. Please do not open a public issue for a security problem. This is a
one-person project, answered as time allows; a fix lands as a normal pull request that names the
report once it is public.

In scope: code and configuration in this repository, including the compose file, the Airflow DAG,
the gateway configuration, the agent hooks and checkers, and the overlay patches in
`infra/auto-ontology/patches/`.

Out of scope: NVIDIA Auto Ontology itself, LiteLLM, Langfuse, Airflow and other upstream projects
(report those to their maintainers); findings that need the stack exposed beyond `127.0.0.1`,
which this project never does; and the accepted risks below.

## Security model

- **Local only.** Every published port binds to `127.0.0.1`; the Auto Ontology containers sit on an
  internal network with no route out, so the gateway is their only way to a model.
- **Secrets** live in the gitignored `.env` (mode 0600), created by `make env-secrets`. Provider
  keys are passed to the gateway only; the Airflow containers never see `.env` and get the four
  keys their tasks need.
- **Coding agents** work under `AGENTS.md`: a branch per issue, no merge, no reading `.env`. The
  Claude Code hooks in `.claude/hooks/` enforce part of that; they are guardrails, not a sandbox.
- **Supply chain.** Images are pinned by digest, GitHub Actions by commit, Python packages by
  `uv.lock`; Dependabot proposes updates and CodeQL scans the Python code. CI runs gitleaks and
  `helpers/check_secrets.py`.

## Accepted risks

Each was decided by the owner; the worknote named holds the reasons.

- **Airflow has no login.** Every visitor of `127.0.0.1:8080` is an admin
  (`AIRFLOW__CORE__SIMPLE_AUTH_MANAGER_ALL_ADMINS`). Anything that reaches the port can trigger
  runs; DAG run values never reach a shell command (`docs/task-management/40-security-phase-1.md`).
- **The gateway master secret is in the Airflow tasks**, which read the spend log with it
  (`docs/task-management/40-security-phase-1.md`).
- **The rerank route takes no key.** LiteLLM OSS cannot key a pass-through route, so any local
  process or container on the `wh` network can spend the NVIDIA key through
  `/nvidia/rerank-8b/reranking` (`infra/llm-gateway/config.yaml`; owner decision 2026-11-23,
  issue #44).

Before exposing any part of the stack beyond one machine: real Airflow authentication, TLS, and a
keyed rerank route (or a proxy in front of it) are required.
