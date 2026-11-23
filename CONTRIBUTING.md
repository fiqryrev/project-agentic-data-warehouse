# Contributing

This repository is built by coding agents and one person, under a written work loop that CI
enforces. A contribution, from a person or an agent, follows the same loop.

## Start here

- [AGENTS.md](AGENTS.md): the map of the repository, the work loop, the five hard rules, the
  worknote and PR body formats, and every blocking check. Read it first.
- [docs/runbook.md](docs/runbook.md): run the stack from a fresh clone.
- [SECURITY.md](SECURITY.md): report a vulnerability privately, never in a public issue.

## The loop, in short

1. **An issue** for the work ([templates](.github/ISSUE_TEMPLATE/): bug, task, label batch).
2. **A plan agreed in the issue or chat** before any edit.
3. **A branch named `<issue>-<slug>`**, in its own worktree; never commit on `main`.
4. **The change, its tests and a worknote** `docs/task-management/<issue>-<slug>.md` in one PR.
5. **The PR body** has a Pre-merge list where every item ends in `→ PASS`, `→ FAIL: reason` or
   `→ SKIP[rule]: reason`, and ends with the AI usage footer (`helpers/ai_usage_footer.py`).
6. **Checks pass** (below), review comments are answered, and **the owner merges**. Nobody else
   merges, and an agent never does.

## Checks

Run these before opening a PR; CI runs the same and blocks on any failure.

```bash
make test
```

```bash
make lint
```

```bash
make checks
```

```bash
make dbt-ci
```

`check_worknote` and `check_pr_body` run in CI on the PR itself. Dependabot's patch and minor
updates skip those two (they cannot write a worknote); a major upgrade is planned as its own issue.

## Ground rules

- No secrets, home paths or personal identifiers in any file; never read or print `.env`.
- Every number in a PR, worknote or answer cites the SQL or command behind it.
- Model calls go through the LiteLLM gateway only (`check_gateway_only`).
- Changes to NVIDIA Auto Ontology are overlay patches in `infra/auto-ontology/patches/`, never a
  fork or an upstream PR from this repository.

## License

Contributions are made under the [Apache License 2.0](LICENSE), the licence of this repository.
