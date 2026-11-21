# 4: M1 repo skeleton and agent harness

## Goal

PLAN section 11, row M1: `AGENTS.md` with the work loop, the harness registry, hooks, the
activity log, blocking CI (entry size, parity, secrets, worknote, PR body, pricing), the
pricing file and the AI usage footer helper with tests. Done when a PR without a worknote,
with an untokened pre-merge item, or without the AI usage footer fails CI, and this PR's
own footer is rendered by the helper.

## Plan (as approved)

Build the files listed in PLAN sections 8.7, 9 and 10 that M1 needs, nothing from later
milestones. Seed `model-pricing.yaml` from the official Anthropic pricing page with the
prices given for 2026-11-21. Ask the owner before pushing or opening the PR; never merge.

## Decisions

- **Python via uv, `pyproject.toml` with `package = false`.** Helpers run as
  `uv run python -m helpers.<check>`; hooks and the activity logger use the standard library
  only, so they run with a bare `python3` from the Claude Code hook.
- **Issue number from the PR body or the branch.** `check_worknote` reads `Closes #N` (or
  Fixes/Resolves/Refs) first, then a branch named `<issue>-<slug>`. Agent-created branches
  such as `claude/...` therefore need `Closes #N` in the body.
- **A `→ FAIL:` pre-merge item blocks the merge**, not only an untokened one: the token says
  what happened, and a failed check should not merge.
- **Footer counts one entry per message id**, keeping the entry with the largest output
  count (the final usage of a streamed message), across the main transcript and
  `subagents/*.jsonl`. Cache writes without a TTL split are priced as 5-minute writes.
- **Effort** comes from the transcript's `effort` field, then `output_config.effort`, then
  `perTurnEffort`, then the last `api-request` `output_config.effort` in the same file.
- **Ledger.** The hidden comment stores `{from, to}` per session. A new footer starts after
  the latest `to` found in earlier PR bodies (`--prior-body` or `--prior-from-gh`);
  re-rendering the same PR keeps its own `from`, so it does not shrink.
- **Unknown model fails loudly** instead of pricing at zero.
- **`check_pr_body` checks the footer arithmetic**: total equals input plus output, output
  cache hit is `(0, $0.00)`, total cache hit equals the input cache hit.
- **Secrets:** `check_secrets` (home paths, provider key shapes, tracked env files) plus
  gitleaks in CI. The write hook reuses the same patterns.
- **Rule files:** budget of 40 lines, 4,000 bytes and 200 characters per line each.
- **Bash guard checks the repository Git would use** (Codex review on PR #5): it follows
  `cd <dir>` inside the command and Git's global `-C`, `--git-dir` and `--work-tree`, so
  `git -C <main checkout> commit` from an issue worktree is blocked. Push refspecs whose
  destination is the default branch, and `--all`/`--mirror`, are read from the arguments.
- **MCP duty** is declared `none` with a reason; no MCP server is wired yet.
- Pricing `source_url` is `https://platform.claude.com/docs/en/about-claude/pricing`
  (the official docs page, which lists the cache-write rates; the marketing URL redirects).

## Done

- `uv run pytest -q` → 60 passed (footer, each checker, hooks, activity log).
- `uv run python -m helpers.check_entry_size`, `check_harness_parity`, `check_secrets`,
  `check_prices` → OK on this branch.
- `uv run python -m helpers.check_pr_body --body-file tests/governance/fixtures/pr_bodies/bad_untokened.md`
  → exit 1. The bad fixtures (`bad_untokened`, `bad_no_footer`, `bad_watermark`,
  `bad_footer_shape`, `bad_no_sections`) each fail in `tests/governance/test_check_pr_body.py`;
  `test_check_worknote.py` builds a throwaway git repo whose branch lacks the worknote and
  shows the CLI exit 1, then 0 once the worknote is added.

## Open

- Branch protection must require the `governance` and `gitleaks` checks (owner setting).
- Version pins from `docs/m0-findings.md` go into compose and dbt files in M3, M4, M8, M9;
  nothing in M1 runs those components.
- Later checkers (`check_naming`, `check_bundle`, `check_layers`, `check_audit_columns`,
  `check_knowledge`, `check_gateway_only`, `check_duckdb_compat`) arrive in M3 to M6.
