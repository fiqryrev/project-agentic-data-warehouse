# AGENTS.md

The map and the work loop for any coding agent in this repository. Keep it under 200 lines
(`check_entry_size`). Details live in skills and rule files that load only when used.

## What this repository is

A local data warehouse (DuckDB, dbt, Airflow) whose serving file feeds NVIDIA Auto Ontology,
with every model call going through a LiteLLM gateway traced in Langfuse. `PLAN.md` is the
design; `docs/m0-findings.md` holds the verified versions and commands.

## Map

| Path | What it holds |
|---|---|
| `PLAN.md` | design and milestones (section 11) |
| `generator/` | deterministic source data (`uv run python -m generator --date <d>`); see `generator/DEFECTS.md` |
| `loader/` | landing -> `lake.<source>__<table>` with audit columns (`uv run python -m loader --date <d>`) |
| `dbt/` | dbt v2 project: `models/{staging,warehouse,mart}/<domain>/`, targets dev, ci, prod (Airflow only) |
| `infra/duckdb-pins.yaml` | DuckDB builds that must open one file (loader, dbt, Auto Ontology) |
| `Makefile` | `make test`, `make checks`, `make generate`, `make load`, `make dbt-build`, `make dbt-ci` |
| `.agents/rules/` | one line per rule; the story behind each in `.agents/rules/history/` |
| `.agents/skills/` | working procedures, loaded on use (`.claude/skills` points here) |
| `.agents/harnesses.yaml` | registry of wired agent tools and their six duties |
| `.agents/toolbelt.md` | every CLI and server: owner, access, reason, review date |
| `.agents/ai-usage/model-pricing.yaml` | list prices per token class for the PR footer |
| `.claude/settings.json` | permissions (deny > ask > allow) and the three hooks |
| `.claude/hooks/` | `guard_bash.py`, `guard_write.py` |
| `helpers/` | `check_*.py` checkers, `ai_usage_footer.py`, `log_agent_action.py` |
| `tests/governance/` | one pytest file per checker, with bad fixtures |
| `docs/task-management/` | one worknote per issue: `<issue>-<slug>.md` |
| `.github/workflows/ci.yml` | blocking CI |
| `.agent-activity-logs/` | gitignored; one JSONL file per session |

## The loop

One GitHub issue, one worktree, one worknote, one PR.

0. **Pre-flight.** Is the previous issue closed out? (skill `closeout`, pre-flight part)
1. **Plan in chat; wait for approval.** No edits before this.
2. **Worktree** under `.worktrees/<issue>-<slug>/`, branch named from the issue
   (skill `branch-name`).
3. **Analyse from inside the worktree**; surface scope changes before acting on them.
4. **Issue created or confirmed**, labelled, moved to In Progress (skill `issue-create`).
5. **Work**, plus the worknote and any knowledge entry, in the same commit.
6. **Ask before commit and PR.** The PR body has the test plan with result tokens and ends
   with the AI usage footer (skill `pr-open`).
7. **Close out only when told**: merged and green, issue updated and closed, worktree
   removed (skill `closeout`). Merging is never implied.

## Five hard rules

1. Plan before edit.
2. Branch, never the default.
3. Never merge unless told to merge a named PR.
4. No secrets, home paths or personal identifiers in files.
5. Every number cites its query.

All rules, one line each: `.agents/rules/core.md`.

## Worknote

`docs/task-management/<issue>-<slug>.md`, touched by every PR of that issue
(`check_worknote`). Sections: Goal, Plan (as approved), Decisions (with reasons), Done
(commands run and their results), Open (what is left, follow-ups).

## PR body

```markdown
<summary>

Closes #<issue>

## Pre-merge

- <check> → PASS
- <check> → FAIL: <reason>
- <check> → SKIP[<rule>]: <reason>

## Post-merge

- <step after merge>

## AI usage
```

Render the footer, then check the body:

```bash
uv run python helpers/ai_usage_footer.py render --body-file pr-body.md --prior-from-gh
uv run python -m helpers.check_pr_body --body-file pr-body.md
```

The footer is a fixed six-line `text` block (Harness Tool, Model Name with effort, Input,
Output and Total Token Usage with cache hits, Metadata) plus a hidden ledger line, so the
next PR from the same session counts only new tokens. No tool watermark.

## Activity log

At each decision point and external call, append one line:

```bash
uv run python helpers/log_agent_action.py --role <role> --action <decide|call|check> \
  --tool <tool> --args "<one line>" --result "<one line>" --status <ok|error|blocked|info>
```

The PostToolUse hook logs every tool call the same way. Logs are gitignored.

## Checks (CI, blocking)

| Check | Command |
|---|---|
| tests | `uv run pytest -q` |
| entry size | `uv run python -m helpers.check_entry_size` |
| harness parity | `uv run python -m helpers.check_harness_parity` |
| secrets and home paths | `uv run python -m helpers.check_secrets` (and gitleaks in CI) |
| pricing file | `uv run python -m helpers.check_prices` |
| DuckDB file compatibility | `uv run python -m helpers.check_duckdb_compat` |
| model and column names | `uv run python -m helpers.check_naming` |
| model bundle (YAML, docs, key test) | `uv run python -m helpers.check_bundle` |
| layer reads | `uv run python -m helpers.check_layers` |
| audit columns | `uv run python -m helpers.check_audit_columns` |
| model calls only via the gateway | `uv run python -m helpers.check_gateway_only` |
| worknote | `uv run python -m helpers.check_worknote --base origin/main` |
| PR body | `uv run python -m helpers.check_pr_body --body-file pr-body.md` |
| dbt (job `dbt`) | `make dbt-ci`: 3 generated days, loaded, then `dbt build --target ci` |

The dbt checkers read the project statically (`helpers/dbtlib.py`); model and column rules
are in `.agents/rules/dbt.md`. M6 adds `check_knowledge`.

## Data access

Agents get `SELECT` on the serving snapshot through a read-only connection. Builds run in
`dev` and `ci`. Only Airflow writes the daily build file. Before any
`WHERE col = '<literal>'`, profile the column or cite a `da-` entry verified within 90 days.

## Skills

`issue-create`, `branch-name`, `pr-open`, `closeout`. More arrive with their milestone
(`dbt-add-model`, `run-backfill`, `ontology-refresh`, `knowledge-add`, `verify-literal`,
the analyst and label skills).
