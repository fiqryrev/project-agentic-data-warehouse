# 40: security phase 1

## Goal

Close the real gaps that the 2026-11-23 security review found in the local stack (phase 1): S1
shell injection through DAG run conf, S2 Airflow containers reading every secret, S3 actions
pinned by tag, S6 personal notes not ignored, S9 `.env` mode and the Redis password in arguments.

## Plan (as approved)

Approved in chat on 2026-11-23, with issue #40:

- S1: conf and run id reach the shell only through the task's `env=`; the golden flag renders
  to `true` or `false` only; tests for both, `airflow/backfill.sh` unchanged.
- S2: the four keys the tasks read go into the `x-airflow` environment; `read_env()` prefers
  the environment; `.env` is masked inside the containers; test.
- S3 (code part): every action pinned to a commit SHA looked up with `gh api`.
- S6: `.notes/` in `.gitignore`.
- S9: both `.env` writers leave 0600 (tests); the Redis password leaves the arguments.

## Decisions

- **S1: run id by `env=` too, not only the conf.** The review asked to confirm that Airflow's run
  id pattern forbids a single quote. Passing `RUN_ID` through the environment, always
  double-quoted (`"$RUN_ID"`), removes the question instead of depending on an Airflow setting.
  `append_env=True` on every task with `env=`, or the task would lose the container environment
  (`DBT_*`, URLs, keys).
- **S1: the golden flag is rendered to a fixed word and parsed again** (`llm.golden.enabled`), so
  a hostile conf is harmless even if one layer changes. `jinja2` joins the dev group so the test
  renders the template with a sandboxed Jinja environment and `StrictUndefined`, as Airflow does,
  rather than comparing strings.
- **S2: mask, not a list of mounts.** `/dev/null:/opt/wh/.env:ro` after the repository mount. A
  hand-kept list of folders (`airflow/`, `dbt/`, `llm/`, ...) breaks the day a task reads a new
  one; the mask keeps every path working and hides only the file. Checked with
  `docker compose ... config` on a dummy env file: the mask follows the repository mount.
- **S2: the four keys** come from a grep of `read_env`/`env[` in `llm/` and `publish/`:
  `LANGFUSE_PROJECT_PUBLIC_SECRET`, `LANGFUSE_PROJECT_SECRET` (Langfuse, tasks 7 and 8),
  `LITELLM_MASTER_SECRET` (gateway spend log, tasks 7 and 8), `AO_ADMIN_SECRET` (sign-in to Auto
  Ontology, task 7). All end in `_SECRET`, so `make env-secrets`, which `make up-core` runs
  first, has already generated them: no ordering change between `up-core`, `up-obs` and
  `up-ontology`. No provider key reaches Airflow.
- **S2 step 5: the master secret stays in the Airflow tasks: accepted risk** (owner, in chat,
  2026-11-23). Tasks 7 and 8 read `/spend/logs`, which needs it. The exposure left is a process
  in the scheduler container; S1 closes the known way in.
- **S2: an empty variable does not hide the file.** `read_env()` takes only non-empty values from
  the environment, since compose passes `${KEY:-}` (empty) when `.env` lacks the key.
- **S9: `fchmod` before writing**, so an older 0644 `.env` is narrowed before the secrets go in,
  not after. Both writers keep their own copy for now; M2 (one `.env` module) merges them.
- **S9 Redis: password as config on stdin.** `REDISCLI_AUTH` in the environment serves the health
  check (`redis-cli ping`); the server reads `requirepass` from stdin (`redis-server -`) through a
  heredoc, so the value is in no argument, not even the shell's expansion. The command still
  starts with `docker-entrypoint.sh redis-server`, so the image drops root as before. `docker
  inspect` still shows the environment, as it does for every other service's password.
- **S3: pinned to the commit the current major tag points to** (`actions/checkout` v4.4.0,
  `astral-sh/setup-uv` v6.8.0, `gitleaks/gitleaks-action` v2.3.9): no version change in the
  same PR as the pinning. `tests/pipeline/test_ci_workflow.py` keeps it that way.

## Done

- `gh api repos/<action>/commits/<tag>` for each action; exact tag from the repository's tags.
- `docker compose -f infra/compose.yml --env-file <dummy> --profile core --profile obs config`:
  exit 0; Airflow volumes are the repository, `/dev/null` over `/opt/wh/.env` (read-only) and the
  logs volume; Airflow secrets are the JWT secret plus the four task keys; Redis command and
  health check carry no password.
- Redis start command run in `sh` with a stub `docker-entrypoint.sh`: argv
  `redis-server - --maxmemory-policy noeviction`, stdin `requirepass <value>`.
- `git check-ignore .notes` succeeds.
- `uv run pytest -q`: PASS. `make checks`: PASS.

## Open

- OWNER: branch protection on `main`, add `governance`, `gitleaks` and `dbt` as required checks
  (S3).
- OWNER: `make up-core` and `make backfill FROM=2026-01-01 TO=2026-01-02` with the stack, to
  confirm the tasks read their keys from the environment and the Redis container starts (Docker
  was not running here, so neither was run live).
- Follow-up: a narrower gateway key for `/spend/logs` in place of the master secret, if LiteLLM
  OSS gains one.
- Phases 2 to 4 of the review: separate issues.
- Knowledge: `de-0009` (free text from a DAG run reaches the shell only through the task
  environment).
