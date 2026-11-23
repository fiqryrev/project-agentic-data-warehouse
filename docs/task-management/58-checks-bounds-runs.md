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
  `docs/runs/` (owner's choice), the cited ones stay. Corrected after review: all five are cited,
  so all eight stay (see Decisions).

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
- **M5: every existing report stays in `docs/runs/`** (Codex review on #61). The first version
  removed five compare reports as "cited nowhere", but that check searched for file names
  (`compare-20261122T1238.md`) and missed citations by run id: `refusals-20261122.md` and worknote
  34 cite `T1105`, `T1147`, `T1204` and `T1216`; worknote 36 cites `T1238`. Their p95 latencies and
  verdict changes exist only in those reports, so removing them broke rule 5. All five are back;
  the owner's choice to remove them rested on my wrong claim. Only future reports go to
  `data/runs/`.
- **A test keeps cited reports in git:** `test_every_cited_run_report_is_in_git` collects every
  `compare-<date>T<time>` and `refusals-<date>` id in the tracked Markdown and fails if its report
  is missing from `docs/runs/` (checked: removing `compare-20261122T1238.md` fails it by name).

## Done

- `git grep` of each run id (not only the file name): all eight reports are cited.
- `uv lock`: project 0.0.0 -> 0.1.0, nothing else changed.
- `uv run pytest -q`: PASS. `make checks`: PASS (`check_knowledge` still resolves `de-0008`'s
  evidence in `refusals-20261122.md`).

## Open

- Knowledge: no new lesson.
