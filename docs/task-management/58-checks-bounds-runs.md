# 58: one checks list, dependency bounds and version, run reports out of git (M3, M4, M5)

## Goal

Phase 3 of the 2026-11-23 review: M3 (the twelve checkers listed by hand in `Makefile` and
`ci.yml`), M4 (`pyarrow` and `pyyaml` without an upper bound; version `0.0.0`), M5 (seven compare
reports in `docs/runs/` from one day).

## Plan (as approved)

Approved in chat on 2026-11-23 with phase 3 (issues #57, #58, #59):

- M3: a test fails when the two lists differ; CI keeps one step per checker.
- M4: upper bounds on the major version; version 0.1.0.
- M5: `llm/compare.py` writes to `data/runs/` (gitignored); the five uncited compare reports leave
  `docs/runs/` (owner's choice), the cited ones stay.

## Decisions

- **M3: a parity test, not `make checks` in CI.** One CI step per checker names the failing
  checker in the run summary, and every step runs after a failure (`success() || failure()`).
  `make checks` stops at the first failure. `test_makefile_checks_and_ci_run_the_same_checkers`
  compares the two lists in order; `check_worknote` and `check_pr_body` run in CI only (they need
  a PR).
- **M4: `pyarrow>=26.0.1,<27`, `pyyaml>=6,<7`** (`duckdb` already had `<1.6`). `uv.lock` decides
  installs; the bounds stop a re-lock from crossing a major silently, and Dependabot ignores majors
  anyway (#52). A test requires an upper bound on every runtime dependency.
- **M4: version 0.1.0:** the first release-shaped state (M0 to M12 done, phase 1 and 2 security
  fixes in). `uv lock` updated the project's own entry only.
- **M5: reports in `data/runs/`.** A comparison writes a report per run; most are working output.
  `data/` is already gitignored. A report worth citing is copied to `docs/runs/` by hand and linked.
  `PLAN.md` 8.6, `docs/runbook.md`, the comparison mart's doc and the Makefile comment say so.
- **M5: what stays in `docs/runs/`:** `compare-20261122T0958.md` and `compare-20261122T1006.md`
  (cited by the README and worknote 32), `refusals-20261122.md` (README, `de-0008` evidence). The
  five others (`T1105`, `T1147`, `T1204`, `T1216`, `T1238`) were cited nowhere (`git grep` of each
  file name) and are removed from the tree; they stay in git history.

## Done

- `git grep -l <report name>` for each of the eight reports: three cited, five not.
- `uv lock`: project 0.0.0 -> 0.1.0, nothing else changed.
- `uv run pytest -q`: PASS. `make checks`: PASS (`check_knowledge` still resolves `de-0008`'s
  evidence in `refusals-20261122.md`).

## Open

- Knowledge: no new lesson.
