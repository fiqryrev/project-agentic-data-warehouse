# 78: upgrade gitleaks/gitleaks-action to v3.0.0 (Node 24)

## Goal

After #76 the `gitleaks` job still logged "Node.js 20 is deprecated ... being forced to run on
Node.js 24: gitleaks/gitleaks-action@ff98106..." (`main` run 45786388112). The pin was v2.3.9,
`using: "node20"`. Move to v3.0.0, the Node 24 release. Dependabot ignores Actions majors, so
this is its own issue.

## Plan (as approved)

Approved in chat on 2026-11-26: pin `gitleaks/gitleaks-action` v3.0.0 by commit SHA with the
version comment in `ci.yml`; worknote with the lookup and the v2.3.9 to v3.0.0 comparison; no
tag-only pins, workflows parse, tests and checks; on the PR, the `gitleaks` job green with no
Node.js 20 warning before merge.

## Decisions

- **Target from the API:** `gh api repos/gitleaks/gitleaks-action/git/ref/tags/v3.0.0` (tag
  object dereferenced) gives `e0c47f4f8be36e29cdc102c57e68cb5cbf0e8d1e`; its `action.yml` says
  `using: "node24"`.
- **What changed, read from `gh api .../compare/ff98106...e0c47f4`:** 5 commits. In the action
  itself, `action.yml` runtime `node20` to `node24` and `package.json` `@actions/core` 1.10.0 to
  ^1.11.1; the rest is the rebuilt `dist/index.js`, lock file, README and the project's own
  workflows. The release notes say no change to inputs, outputs or behaviour. CI passes no
  inputs, only `GITHUB_TOKEN`, so nothing else changes.
- **Why now:** the v3.0.0 notes say GitHub removed Node 20 from hosted runners on 2026-09-16;
  v2 runs today only because the runner forces it onto Node 24.
- **#76 missed this:** its plan quoted the warning from the `governance` job log, which names
  only the actions that job uses. The `gitleaks` job logs its own warning.

## Done

- `grep -E 'uses: .*@v[0-9]' .github/workflows/*.yml`: no matches (no tag-only pins).
- `yaml.safe_load` on `ci.yml`: parses.
- `uv run pytest -q`: PASS (411). `uv run ruff check .`: PASS. `make checks`: every checker OK
  up to `check_golden`; `check_worknote` reads committed files, so it runs after the commit.

## Open

- On the PR, before merge: the `gitleaks` job green and no Node.js 20 warning in any job log.
