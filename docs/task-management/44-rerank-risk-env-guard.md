# 44: rerank route risk and the .env Bash guard

## Goal

S5 and S10 of the 2026-11-23 security review. S5: the gateway's rerank pass-through takes no key,
so any local process can spend the NVIDIA key through it. S10: the Bash hook blocked `cat .env`
and a few other printers, but not `grep`, `awk`, `sed`, `source`, `cp`, a redirect, or
`docker compose config`.

## Plan (as approved)

Approved in chat on 2026-11-23 with phase 2 (issues #42, #43, #44):

- S5: owner decision, accepted risk, documented (no proxy).
- S10: block any Bash segment that names `.env` (except `.env.example` and `--env-file .env`)
  and `docker compose ... config`; cases in `tests/governance/test_hooks.py`; `AGENTS.md` says
  hooks are guardrails, not a sandbox.

## Decisions

- **S5: accepted risk** (owner, in chat, 2026-11-23): `auth: false` stays. It is reachable only on
  127.0.0.1 and the private networks; a proxy would add a container and a shared secret for a
  laptop. Recorded in three places a reader meets it: `SECURITY.md` (Accepted risks, added with
  #42), the README's Limits, and the comment on the route in `infra/llm-gateway/config.yaml`.
- **S10: match the file, not the command.** The old rule listed printers (`cat`, `head`, ...);
  any list misses one. The guard now blocks a segment in which any token is the file: `.env`,
  `./.env`, `<dir>/.env`, `<.env`, `$(<.env)`. `.env.example` and `.envrc` do not match.
- **`--env-file .env` stays allowed for Compose only** (both spellings): Compose reads the file
  for interpolation and prints nothing; the Makefile's compose lines use it, and a test runs each
  of them through the guard. The first version exempted the flag for any command; Codex (review
  on #47) showed `docker run --env-file .env alpine env` prints the values, so other commands
  with the flag are blocked.
- **Globs and braces count** (Codex review on #47): a token the shell expands to `.env` is
  blocked: `.env*`, `.e?v`, `.[e]nv`, `.*`, `{.env,x}`, `.{env,x}`. A glob reaches a dotfile only
  when its last part starts with a dot (no `dotglob`), so `*` and `*.md` stay allowed.
- **`docker compose ... config` is blocked** whatever its flags: it prints every interpolated
  value. `docker config` (swarm) and `git config` are not compose and stay allowed.
- **Harmless commands that name the file are blocked too** (`ls .env`, `git check-ignore .env`):
  the guard is conservative; the owner runs those.
- **Guardrail, not sandbox**, said in the hook's docstring and in the AGENTS.md map row: a command
  that never names the file (`grep -r` over the tree, a script opening it) is not caught. The
  `Read(./.env)` deny rule covers the Read tool; nothing covers every Bash path.

## Done

- Probe of `guard_bash.env_file_reasons` on 25 commands: every read form blocked, the allowed
  forms (`cat .env.example`, compose with `--env-file`, `make up-core`, `git config`,
  `docker config ls`) pass.
- `uv run pytest -q tests/governance/test_hooks.py`: 12 passed.
- `uv run pytest -q`: PASS. `make checks`: PASS.

## Open

- Merge after #42: the README's Limits links `SECURITY.md`, which #42 adds.
- OWNER, if the stack is ever exposed: key the rerank route or put a proxy in front (review S5,
  option one).
- Knowledge: no new lesson.
