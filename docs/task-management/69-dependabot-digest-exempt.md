# 69: Dependabot digest-only bumps are not exempt from worknote and PR body checks

## Goal

Dependabot PR #68 (`chainguard/minio` digest bump in `infra/compose.yml`) failed the `governance`
job at `check_worknote` and `check_pr_body`. A Dependabot patch or minor PR should skip those two
checks (#52). Make digest-only bumps skip them too, without opening a gap for pushed commits or
major updates.

## Plan (as approved)

Approved in chat on 2026-11-26: in `dependabot_pr()`, also exempt a commit with the
`updated-dependencies` block, no `update-type`, and a 64-hex digest as every `dependency-version`.
Majors and commits without Dependabot metadata keep the full checks. Tests in
`test_check_worknote.py` and `test_check_pr_body.py`; `make checks` and `pytest` pass.

## Decisions

- **Cause:** `dependabot_pr()` exempted a commit only when it had an `update-type:` line. The
  minio image is pinned by digest only (`cgr.dev/chainguard/minio@sha256:...`, no tag), so
  Dependabot has no version to compare and writes no `update-type`. The checker read that as
  "someone pushed to the branch".
- **Rule:** a commit is safe when it has `updated-dependencies:` and either non-major
  `update-type` values, or no `update-type` and every `dependency-version` a digest (bare 64 hex
  or `sha256:` prefixed). Mixing a digest with a tag version, a block with no versions, a short
  digest, or a commit with no metadata block stays on the full checks.
- **Why a digest bump is safe to exempt:** with no tag, the bump only moves to the newest build
  of the same image line; there is no major version to skip past. Every other check (tests,
  dbt, gitleaks, CodeQL) still runs, and the owner still merges.
- `dependabot_update_types()` was only used inside `govlib.py`; it became
  `dependabot_messages()` plus `dependabot_safe_commit()`.

## Done

- `uv run pytest -q tests/governance/test_check_worknote.py tests/governance/test_check_pr_body.py`:
  PASS (27).
- `dependabot_pr()` on PR #68's real commit range (`git merge-base origin/main <head>..<head>`):
  `True` (was `False`).
- `uv run pytest -q`: PASS (410). `uv run ruff check .`: PASS. `make checks`: every checker OK
  up to `check_golden`; `check_worknote` reads committed files, so it runs after the commit.

## Open

- After merge: `@dependabot rebase` on #68; its `governance` job should pass.
- Knowledge: no new entry; the rule lives in the `dependabot_safe_commit()` docstring.
