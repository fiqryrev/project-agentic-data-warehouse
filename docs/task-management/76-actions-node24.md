# 76: upgrade actions/checkout and astral-sh/setup-uv to Node 24 majors

## Goal

CI logs warn that Node.js 20 is deprecated and that `actions/checkout` and `astral-sh/setup-uv`
are forced onto Node.js 24. Both were pinned to Node 20 majors (checkout v4.4.0, setup-uv
v6.8.0, pinned in #40). `.github/dependabot.yml` ignores majors for GitHub Actions, so this is
its own issue. Move both to their current majors.

## Plan (as approved)

Approved in chat on 2026-11-26: pin `actions/checkout` v7.0.1 and `astral-sh/setup-uv` v10.4.0
by commit SHA with the version comment, in `ci.yml` (three checkout, two setup-uv) and
`codeql.yml` (one checkout); review the breaking changes in between; no tag-only pins; tests and
checks; CI green with no Node.js 20 warning.

## Decisions

- **Targets from the API, not guessed:** `gh api repos/<repo>/git/ref/tags/<tag>` (tag object
  dereferenced where annotated). checkout v7.0.1 is `3d3c42e5aac5ba805825da76410c181273ba90b1`,
  setup-uv v10.4.0 is `1db35dd8eee11c5894872e0b383ae6c406cf738d`; `action.yml` at both says
  `using: node24`, and every setup-uv input the CI uses (`enable-cache`) is still there.
- **Breaking changes reviewed** (release notes of each `vN.0.0`), none affect this CI:
  - checkout v5 Node 24; v6 persists credentials to a separate file (no step pushes with them;
    gitleaks only reads history); v7 dependency bumps.
  - setup-uv v7 Node 24, `server-url` removed (unused), respects an existing `UV_CACHE_DIR`;
    v8 removes the old manifest format and floating major tags (we pin a SHA, no manifest);
    v9 `prune-cache` defaults to `false` (cache may grow a little); v10 `enable-cache: auto`
    turns the cache off for `pull_request_target`, `workflow_run` and `release` (we set
    `enable-cache: true` and run on `pull_request`, `push` and `schedule` only).
- **v10.4.0 is 8 days old** (2026-11-18); the repo has no minimum-age rule, and the owner
  approved it over v10.3.3.
- codeql-action and gitleaks-action stay: the warning does not name them.

## Done

- `grep -E 'uses: .*@v[0-9]' .github/workflows/*.yml`: no matches (no tag-only pins).
- `yaml.safe_load` on `ci.yml` and `codeql.yml`: both parse.
- `uv run pytest -q`: PASS (411). `uv run ruff check .`: PASS. `make checks`: every checker OK
  up to `check_golden`; `check_worknote` reads committed files, so it runs after the commit.

## Open

- On the PR: every job green, and the Node.js 20 deprecation warning gone from the job logs.
- The Dependabot majors filter stays; the next Actions major is again its own issue.
