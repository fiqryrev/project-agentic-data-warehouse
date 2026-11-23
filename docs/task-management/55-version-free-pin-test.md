# 55: version-free Airflow and uv pin test, so Dependabot bumps can pass

## Goal

Dependabot's Airflow bump (#48) failed one test after #53: `test_dockerfile_pins_airflow_and_uv`
looked for the exact text `apache/airflow:3.3.2-python3.12@sha256:` and `uv:0.11.8@sha256:`.
Every bump of either would fail it, and fixing the test inside the Dependabot PR would add a
foreign commit and cost the PR its exemption (#52).

## Plan (as approved)

Approved in chat on 2026-11-23:

1. The test checks the shape of the pins (any version, a 64-hex digest), not fixed versions.
2. The locally built image is named `wh-airflow:local` instead of `wh-airflow:3.3.2`.
3. README and toolbelt keep naming the Airflow version; they are updated when an upgrade is
   adopted, not checked by a test (that would block Dependabot again).

## Decisions

- **Shape, not version:** `FROM apache/airflow:<x.y.z>-python3.12@sha256:<64 hex>` and
  `--from=ghcr.io/astral-sh/uv:<x.y.z>@sha256:<64 hex>`. The digest rule from #42 stays
  (`test_every_dockerfile_base_is_pinned_by_digest`); only the version is free. I put the fixed
  version into the test in #42; it only needed the digest.
- **`wh-airflow:local`:** the image is built here from `airflow/Dockerfile`, which carries the
  version. A name with `3.3.2` would go on saying so after Dependabot moves the base, and only a hand
  edit could fix it. A test keeps the name free of a version.
- **Docs are not checked** for the Airflow version (`README.md` Tech stack, `.agents/toolbelt.md`):
  a test there would fail every Dependabot bump again. They are updated by whoever adopts the
  upgrade after running it.

## Done

- The new pattern accepts #48's `FROM apache/airflow:3.4.0-python3.12@sha256:818f94af...`
  (`gh pr diff 48`).
- `uv run pytest -q tests/pipeline/test_airflow_files.py`: 24 passed.
- `uv run pytest -q`: PASS. `make checks`: PASS.

## Open

- After merge, Dependabot rebases #48 (or comment `@dependabot rebase` on it).
- OWNER, before merging #48 (Airflow 3.4.0): `make up-core` (runs `airflow db migrate` on the
  metadata database, hard to undo) and `make backfill FROM=2026-01-01 TO=2026-01-02`; then
  update the version in `README.md` and `.agents/toolbelt.md`.
- The first `make up-core` after this builds `wh-airflow:local`; the old `wh-airflow:3.3.2` image
  stays until `docker image rm wh-airflow:3.3.2`.
- Knowledge: no new lesson.
