# 57: one .env module for every reader and writer (M2)

## Goal

Phase 3 of the 2026-11-23 review, M2. Four copies read or wrote `.env`
(`airflow/env_secrets.py`, `infra/llm-gateway/bootstrap.py`, `llm/observe.py`,
`llm/gateway_smoke.py`); the 0600 write (S9) and the environment-first read (S2) lived in some
copies only.

## Plan (as approved)

Approved in chat on 2026-11-23 with phase 3 (issues #57, #58, #59): one standard-library module,
`helpers/envfile.py`, that reads (environment first, then the file), writes owner-only and sets
one key; the four callers use it with their behaviour and tests unchanged; the module has its own
tests.

## Decisions

- **Four functions:** `parse`, `read_file` (file only), `read` (non-empty environment over the
  file), `write_private` (0600, `fchmod` before writing), `set_key` (replace or append one line).
  Standard library only, like the hooks.
- **Each caller keeps its behaviour:** `llm/observe.read_env` reads the environment first (the
  Airflow tasks never see the file, #40); the gateway bootstrap and `gateway_smoke` read the file
  only, since they run on the host against `.env` and a stray shell variable must not change
  which key they manage. The public names stay (`read_env`, `set_env`, `parse`, `fill`), so no
  import or test changes.
- **Scripts add the repository root to `sys.path`:** `airflow/env_secrets.py` and
  `infra/llm-gateway/bootstrap.py` run as `uv run python <path>`, where `helpers/` is not
  importable otherwise. Inside Airflow the tasks run from `/opt/wh`, where it already is.
- **One parse rule:** a line is trimmed before the `#` and `=` tests (the former
  `env_secrets.parse`). The other copies trimmed key and value after splitting; for any line of a
  real `.env` the result is the same.
- **A test keeps it one copy:** `test_no_second_env_parser_or_writer` fails if a file in
  `airflow/`, `llm/`, `infra/`, `publish/` or `helpers/` (other than `envfile.py`) uses `os.fchmod`,
  `O_CREAT` or `line.partition("=")`.

## Done

- `uv run python airflow/env_secrets.py <scratch .env> <scratch example>` twice: first `set
  A_SECRET, PLAIN`, mode 600; then `up to date`.
- `uv run python infra/llm-gateway/bootstrap.py check-keys` runs (names the missing keys: this
  worktree has no `.env`).
- `uv run pytest -q`: PASS (403). `make checks`: PASS.

## Open

- Knowledge: no new lesson.
