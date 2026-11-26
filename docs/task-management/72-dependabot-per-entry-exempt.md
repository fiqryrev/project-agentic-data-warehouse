# 72: Dependabot exemption judges each grouped dependency, not the whole commit

## Goal

After #69, `dependabot_safe_commit()` exempted a commit when it had any `update-type` and none
was major. In a grouped commit, an entry with no `update-type` passed on its neighbours' lines.
PR #71 showed it: `postgres` (17.11-alpine to 17.12-alpine) and `berriai/litellm` (v1.110.2 to
1.111.0) had no `update-type`. Both are minor, but an untyped major would have skipped
`check_worknote` and `check_pr_body` the same way.

## Plan (as approved)

Approved in chat on 2026-11-26, rule chosen "compare major" over "strict": each entry of
`updated-dependencies` qualifies on its own, by a non-major `update-type`, a digest version
(#69), or, with no `update-type`, the same leading major number in its `from A to B` summary
line (a leading `v` dropped). Anything else runs the full checks. Tests; PR #71 stays exempt.

## Decisions

- **Compare major, not strict:** Dependabot leaves out `update-type` for tags it cannot read
  as semver (`17.11-alpine`, a dropped `v`). Under the strict rule most weekly compose PRs would
  need an issue, worknote and footer by hand. The summary line Dependabot writes ("Updates `x`
  from A to B", or "Bumps [x](url) from A to B." for one dependency) gives the old version, so
  the major can be compared directly.
- **Unreadable means not exempt:** no summary line for the entry, or a version without a
  leading number (`latest`), runs the full checks.
- **Calendar versions** (`26.10.4.207`) compare their first number like any other.
- Entries are split on `- dependency-name:` inside the `updated-dependencies` block.

## Done

- New rule over the real commits: PR #71 head, PR #68 (`8609eda`) and every Dependabot squash
  commit on `main` (`7142bee`, `8bef9c1`, `ea8978f`): all `True`.
- `uv run pytest -q`: PASS (411). `uv run ruff check .`: PASS (one E501 on the new regex,
  wrapped). `make checks`: every checker OK up to `check_golden`; `check_worknote` reads
  committed files, so it runs after the commit.

## Open

- Knowledge: no new entry; the rule lives in the `dependabot_safe_commit()` docstring.
- Worktree `.worktrees/69-dependabot-digest-exempt` is still there; remove it at closeout of #69.
