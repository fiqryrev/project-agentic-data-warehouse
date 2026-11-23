# 65: licence, security section, contributor files and current versions (phase 4)

## Goal

Phase 4 of the 2026-11-23 review, description: D1 repository metadata, D2 licence, D3 security
model in the README, D4 contributor files, D5 package description; plus the versions the README
and toolbelt still showed from before #48 and #54.

## Plan (as approved)

Approved in chat on 2026-11-23: one docs PR with D2 to D5 and the versions; owner decisions in
chat: **Apache-2.0** (D2) and setting the suggested description and topics with `gh repo edit`
(D1) once the PR is open.

## Decisions

- **Apache-2.0** (owner): the licence of NVIDIA Auto Ontology, which the overlay patches modify,
  with an explicit patent grant. `LICENSE` is GitHub's Apache-2.0 template (`gh api
  licenses/apache-2.0`), unchanged; `pyproject.toml` gets `license = "Apache-2.0"`.
- **NOTICE:** the copyright line names "the project-agentic-data-warehouse authors", not a person
  (rule 4, no personal identifiers). It says the repository does not contain Auto Ontology's
  source (cloned at build time from the URL in `infra/auto-ontology/bootstrap.sh`, commit in
  `UPSTREAM_SHA`), and that `infra/auto-ontology/patches/` are modifications of it under
  Apache-2.0, as section 4(b) asks. The patches carry no header text, so the notice says where
  the "what" and "why" are (file name, diff, worknote) rather than claiming each patch states it.
- **Per-file change notices, patch 0004** (Codex review on #66): Apache-2.0 section 4(b) asks
  that every modified file carries a prominent notice that it was changed, and a repository NOTICE
  does not do that. `0004-change-notices.patch`, applied last, adds a three-line comment to each of
  the 8 files patches 0001 to 0003 modify or add, naming the patch and where this repository's
  patches are, below NVIDIA's SPDX header, which stays unchanged (section 4(c)). A separate patch
  keeps 0001 to 0003 byte for byte as tested. Generated from a scratch clone at `UPSTREAM_SHA` with
  0001 to 0003 applied; then all four applied in order on a clean checkout, as `bootstrap.sh`
  does, and the 8 files compile. `test_every_patched_file_carries_a_change_notice` fails if a file
  touched by a functional patch has no notice, or if 0004 removes a line.
- **README Security section** (D3), before Limits, linking `SECURITY.md`: local only, Airflow
  without login, where secrets live, what agents may do, supply chain, and what must change
  before exposing anything. It restates `SECURITY.md` in brief; the policy and the accepted risks
  stay in `SECURITY.md` only.
- **Versions:** README tech stack and toolbelt now match `airflow/Dockerfile` and
  `infra/compose.yml`: Airflow 3.4.0, Postgres 17.11, ClickHouse 26.10, Redis 7.4.12, nginx 1.31,
  socket proxy 1.13.2. The CI row names ruff, CodeQL and Dependabot.
- **CONTRIBUTING.md** (D4) points to AGENTS.md rather than repeating it: the loop in six lines,
  the four `make` checks, the ground rules and the licence of contributions.
- **Issue templates** (D4): bug, task and label batch as forms; blank issues off; a contact link
  sends security reports to private vulnerability reporting. The label-batch form says label text
  is quoted data (#43).
- **D5:** the package description is the repository description (D1), so both say the same.

## Done

- `gh api licenses/apache-2.0 --jq .body > LICENSE` (202 lines).
- The bootstrap clones `https://github.com/NVIDIA/auto-ontology.git` (`infra/auto-ontology/bootstrap.sh`),
  the URL in NOTICE.
- The issue templates parse as YAML.
- Scratch clone at `f3c310c7`: patches 0001 to 0004 apply in order with `git apply`; 8 files carry
  the notice; `python3 -m py_compile` on them passes.
- `uv run pytest -q`: PASS. `make lint`: PASS. `make checks`: PASS.

## Open

- After merge: check that GitHub detects the licence (it reads `LICENSE` from `main`). The
  description and nine topics were set with `gh repo edit` once #66 opened.
- OWNER (from phase 1 to 3, still open): required status checks on `main` with "require branches
  to be up to date"; Dependabot alerts, Dependabot security updates and private vulnerability
  reporting (the issue template's security link needs it); auto-delete head branches, remove
  merged branches, disable merge commits; S11, a noreply commit email.
- OWNER: `make up-ontology` rebuilds Auto Ontology with patch 0004 on the next start (comments only;
  no behaviour change).
- Knowledge: no new lesson.
