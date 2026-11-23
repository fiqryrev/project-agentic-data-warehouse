# Why the core rules exist

Each entry: rule number, date added, the reason. Read on demand; not loaded by default.

- 1, 2026-11-21: edits made before the plan is agreed tend to be thrown away; a plan in chat is cheap to change.
- 2, 2026-11-21: `main` is protected (PR required, linear history); a worktree per issue keeps parallel sessions apart.
- 3, 2026-11-21: merging publishes the change; the owner keeps that decision. The Bash hook blocks `gh pr merge`.
- 4, 2026-11-21: the repository is public. `check_secrets` and gitleaks run in CI; the write hook blocks it earlier.
- 5, 2026-11-21: numbers without a query cannot be checked or repeated (PLAN section 7).
- 6, 2026-11-21: commits, pushes and PRs are outward-facing; `.claude/settings.json` puts them under `ask`.
- 7, 2026-11-21: filtering on a misspelled or retired value returns zero rows that look like a real answer.
- 8, 2026-11-21: the worknote is where "why" survives; the footer makes the coding agent's cost visible per PR (PLAN 8.7).
- 8, 2026-11-23: Dependabot cannot open an issue or write a worknote and footer, so its first PRs (#48 to #51) could never pass; the owner exempted its own PRs, limited to patch and minor updates (#52).
- 9, 2026-11-21: an unticked test-plan line hides whether it ran; a token says what happened.
- 10, 2026-11-21: the activity log lets a later session see what was decided and called.
- 11, 2026-11-21: keys for NVIDIA, OpenRouter and Langfuse are personal; `.env` is gitignored and denied to reads.
- 12, 2026-11-21: a read-only connection keeps an agent from damaging the file Auto Ontology serves.
