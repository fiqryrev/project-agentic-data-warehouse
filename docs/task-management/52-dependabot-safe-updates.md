# 52: Dependabot proposes safe updates only, and its PRs pass the repo checks

## Goal

The first Dependabot run (#48 to #51, from the configuration added in #42) showed two gaps: major
versions arrived in the weekly groups, and no Dependabot PR could pass `check_worknote` and
`check_pr_body`.

## Plan (as approved)

Approved in chat on 2026-11-23:

1. `.github/dependabot.yml` proposes patch and minor updates only; DuckDB stays within the range
   in `infra/duckdb-pins.yaml`.
2. Dependabot PRs pass the repo rules: the owner chose to exempt them from the worknote and PR
   body checks (option "exempt `dependabot[bot]`", over an agent adopting each PR).
3. Close #50 and #51; keep #48 and #49 to adopt as their own changes.

## Decisions

- **What the first run showed** (`gh pr view` and the CI logs of #48 to #51):
  - #50 DuckDB 1.5.6 to 2.0.0: `check_duckdb_compat` failed, since DuckDB 1.5.4 (dbt) and 1.5.5
    (Auto Ontology) could not open the file 2.0 wrote, and the dbt job failed on the storage format.
  - #51 compose images: Postgres 17.6 to 19.0 (would not start on the existing `airflow-db` and
    `obs-db` volumes without `pg_upgrade`), Redis 7.4 to 8.10, ClickHouse 26.3 to 26.10, nginx
    1.28 to 1.31, MinIO, socket-proxy 1.13.1 to 1.13.2. CI never starts the stack, so its green
    checks said nothing about these.
  - #48 Airflow 3.3.2 to 3.4.0: one test pins the 3.3.2 tag; the image name and docs too.
  - #49 actions: checkout v4 to v7, setup-uv v6 to v10, gitleaks-action v2 to v3; CI ran on them.
  - All four failed `check_worknote` and `check_pr_body`, which nothing in a Dependabot PR can meet.
- **Ignore majors in every ecosystem** (`version-update:semver-major` for `*`): a major is a
  planned change with its own issue, a worknote and, for images, a run of the stack by the owner.
  This was missing from #42's configuration; my oversight there.
- **DuckDB: minors ignored too.** The loader, dbt and Auto Ontology must open one file
  (`infra/duckdb-pins.yaml`, `loader: ">=1.5.5,<1.6"`), so DuckDB moves only by hand, with the pins
  and `check_duckdb_compat`. A test keeps the ignore and the pin's upper bound together.
- **Exempt by author and branch**, both: `dependabot[bot]` as the PR's user and a head branch
  starting `dependabot/` (`helpers/govlib.py`, `dependabot_pr`). A person cannot open a PR as the
  bot, and a person's PR on a look-alike branch is still checked. Only when the body comes from the
  PR event: `--body-file` (an agent checking its own draft) is never skipped.
- **Every other check still runs** on a Dependabot PR (tests, the other checkers, dbt, gitleaks,
  CodeQL), and the owner still reviews and merges. Rule 8 in `.agents/rules/core.md`, its history
  and the AGENTS.md Worknote section say so.
- **#49 and #48 are kept, not closed:** both are worth having, but as majors (#49) or with test and
  doc changes (#48) they are adopted as their own issues. Dependabot may close #49 itself once
  majors are ignored.

## Done

- `uv run pytest -q tests/governance/test_check_worknote.py tests/governance/test_check_pr_body.py
  tests/pipeline/test_ci_workflow.py`: Dependabot PR skipped; the same PR by a person, and the bot
  on a non-Dependabot branch, still fail; the config ignores majors in all four ecosystems and
  DuckDB minors. PASS.
- `uv run pytest -q`: PASS. `make checks`: PASS.

## Open

- After merge: close #50 and #51 with a note (done in this session, owner approved the plan).
- Adopt #49 (actions majors) and #48 (Airflow 3.4.0, its test, image name and docs) as separate
  issues; Airflow needs a backfill by the owner.
- Plan the image majors when wanted: Postgres 19 (dump and restore, or `pg_upgrade`), Redis 8,
  DuckDB 2 (only when dbt and Auto Ontology support it).
- Knowledge: no new lesson.
