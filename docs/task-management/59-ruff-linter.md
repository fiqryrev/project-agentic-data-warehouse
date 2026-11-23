# 59: ruff linter with a security rule set in CI (M1)

## Goal

Phase 3 of the 2026-11-23 review, M1: `pyproject.toml` had only pytest. Add `ruff` with a modest
rule set, including the security rules, and a CI step; fix or explicitly ignore what it finds,
without reformatting the tree.

## Plan (as approved)

Approved in chat on 2026-11-23 with phase 3 (issues #57, #58, #59): `ruff` in the dev group, rules
`E, F, I, B, UP, S`, line length 120, a CI step; per-folder ignore for `assert` in tests; explicit,
reasoned ignores for `subprocess` and `urlopen` on our own commands and URLs; the rest fixed one by
one.

## Decisions

- **Starting point** (`uvx ruff check --select E,F,I,B,UP,S --line-length 120 --statistics`): 755
  findings; 634 `S101` (assert) in tests, 36 `E501`, 18 `S603`, 16 `S608`, 12 `S607`, 11 `S310`,
  7 `I001`, 6 `B905`, 4 `S105`, 2 `B007`, 2 `S311`, 2 `UP017` and 1 each of `E741`, `F401`,
  `UP031`, `UP033`, `UP037`.
- **Ignored project-wide: `S603`, `S607`.** Every `subprocess` call takes an argument list, never
  a shell, and runs our own tools (git, gh, uv, docker); `S607` only notes they come from PATH.
- **Ignored per file: `S310`** in the five HTTP clients of our own services (gateway bootstrap,
  `ask`, `gateway_smoke`, `observe`, `refresh_ontology`): every URL is an http(s) address from a
  constant or an environment variable, never from data. A new `urlopen` elsewhere is flagged.
- **Ignored in tests:** `S101` (assert), `S105`/`S106`/`S108` (throwaway passwords and temp paths),
  `E501` (long fixture rows).
- **`S608`, per line** with the reason on the line (`identifiers only; values bound with ?`): all
  16 sites interpolate schema, table and column names from our constants or DuckDB's catalog, and
  bind every value. Per line, so a new SQL string in the same file is still flagged.
- **Fixed:** 13 by `ruff --fix` (import order, `datetime.UTC`, `functools.cache`, a quoted
  annotation, an unused import); 6 `zip()` calls get `strict=True` where the lengths are equal by
  construction (footer lines, `re.split` parts, rows and their columns, reference rows and keys,
  questions and their answers, an AST dict), so a mismatch now raises instead of truncating; a
  `%` format became concatenation; 11 long lines in `llm/` wrapped.
- **Kept with a reason on the line:** two `S311` (seeded `random.Random` for deterministic
  synthetic data and for a review sample, not secrets), one `E741` (Arrow type aliases `I, S, D, T`),
  two `B007` (the loop variable is read after the loop, in the failure message).
- **CI step `ruff`** in the governance job, after tests, running even when an earlier step fails;
  `make lint` locally. AGENTS.md (checks table, Makefile row) and the toolbelt list it. No
  `ruff format`: reformatting the tree is not part of this change.
- **Merges last in phase 3:** it touches files #57 and #58 also edit (`llm/observe.py`,
  `llm/gateway_smoke.py`, `infra/llm-gateway/bootstrap.py`, `llm/compare.py`, `pyproject.toml`,
  `uv.lock`, `Makefile`); rebased after they merge.

## Done

- `uv run ruff check .`: All checks passed.
- `uv run pytest -q`: PASS. `make checks`: PASS.

## Open

- Rebase on `main` after #57 and #58 merge, then rerun `ruff`, tests and checks.
- `mypy` (optional in the review): not added.
- Knowledge: no new lesson.
