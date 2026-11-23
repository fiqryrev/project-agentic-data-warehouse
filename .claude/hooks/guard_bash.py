#!/usr/bin/env python3
"""PreToolUse hook for Bash: block the commands the hard rules forbid.

- merging a PR (never merge unless the owner names the PR; the owner runs it);
- committing or pushing while the target repository is on the default branch, pushing to
  the default branch, or pushing every branch at once;
- touching the .env file in any way: any command that names it (`grep`, `awk`, `sed`,
  `source`, `cp`, a `< .env` redirect, ...) or a glob or brace pattern the shell expands to it
  (`.env*`, `.*`, `{.env,x}`), except `--env-file .env` given to docker compose; `.env.example`
  is fine;
- `docker compose ... config`, which prints every variable with its value.

A guardrail against mistakes, not a sandbox: a command that never names the file (`grep -r` over
the repository, a script that opens it) still reads it. The `Read(./.env)` deny rule in
`.claude/settings.json` covers the Read tool.

The target repository is the one Git itself would pick: the hook follows `cd <dir>` inside
the command and Git's global options (`-C <dir>`, `--git-dir`, `--work-tree`), so
`git -C <main checkout> commit` is checked against that checkout's branch, not the
session's. Exit code 2 blocks the call and shows the reason to the agent. Standard library
only.
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
import shlex
import subprocess
import sys
from collections.abc import Callable, Iterator

DEFAULT_BRANCHES = ("main", "master")
RULES = [
    (re.compile(r"\bgh\b[^;&|\n]*\bpr\s+merge\b"),
     "never merge: only the owner merges, and only a PR they name"),
]
ENV_MSG = "never read, print or copy .env; it holds secrets (use .env.example for key names)"
CONFIG_MSG = "never run `docker compose config`: it prints every secret from .env"
# A token that is the .env file: `.env`, `./.env`, `dir/.env`, `<.env`, `$(<.env)`, `X=.env`.
ENV_TOKEN_RE = re.compile(r"(?:^|[/<>=(])\.env\)?$")
BRACE_RE = re.compile(r"\{([^{}]*,[^{}]*)\}")


def _braces(word: str, limit: int = 64) -> list[str]:
    """Shell brace expansion, enough for `{.env,x}` and `.{env,x}`; at most `limit` words."""
    m = BRACE_RE.search(word)
    if not m:
        return [word]
    out: list[str] = []
    for alt in m.group(1).split(","):
        out += _braces(word[:m.start()] + alt + word[m.end():], limit)
        if len(out) >= limit:
            break
    return out[:limit]


def names_env(tok: str) -> bool:
    """True when the shell would turn this token into the .env path: literally, by brace
    expansion, or by a glob (`.env*`, `.e?v`, `.[e]nv`, `.*`). A glob reaches a dotfile only when
    its last part starts with a dot (no `dotglob`), so `*` and `*.md` do not count."""
    for word in _braces(tok):
        if ENV_TOKEN_RE.search(word):
            return True
        base = re.split(r"[/<>=(]", word)[-1].rstrip(")")
        if base.startswith(".") and any(c in base for c in "*?[") and fnmatch.fnmatchcase(".env", base):
            return True
    return False
SEGMENT_SPLIT_RE = re.compile(r"&&|\|\||[;|&\n]")
WRAPPERS = {"sudo", "env", "command", "exec", "nohup", "time", "builtin"}
# Git global options that take a separate value, and the ones that change the target repo.
VALUE_OPTS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env"}
# git push options that take a separate value, so their value is not read as a refspec.
PUSH_VALUE_OPTS = {"-o", "--push-option", "--repo", "--receive-pack", "--exec"}


def current_branch(cwd: str | None, git_globals: tuple[str, ...] = ()) -> str:
    """The branch Git would commit to, given the directory and the global options used."""
    keep: list[str] = []
    i = 0
    while i < len(git_globals):
        opt = git_globals[i]
        if opt in ("-C", "--git-dir", "--work-tree") and i + 1 < len(git_globals):
            keep += [opt, git_globals[i + 1]]
            i += 2
            continue
        if opt.startswith(("--git-dir=", "--work-tree=")):
            keep.append(opt)
        i += 1
    try:
        return subprocess.run(["git", *keep, "branch", "--show-current"], cwd=cwd or None,
                              capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception:
        return ""


def _tokens(segment: str) -> list[str]:
    try:
        toks = shlex.split(segment)
    except ValueError:
        toks = segment.split()
    while toks and (toks[0] in WRAPPERS or re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", toks[0])):
        toks.pop(0)
    return toks


def git_calls(command: str, cwd: str | None) -> Iterator[tuple[str | None, tuple[str, ...], str, list[str]]]:
    """Yield (directory, git global options, subcommand, arguments) for each git call."""
    here = cwd
    for segment in SEGMENT_SPLIT_RE.split(command):
        toks = _tokens(segment)
        if not toks:
            continue
        if toks[0] == "cd":
            target = os.path.expanduser(toks[1] if len(toks) > 1 else "~")
            here = os.path.normpath(os.path.join(here or os.getcwd(), target))
            continue
        if os.path.basename(toks[0]) != "git":
            continue
        i = 1
        while i < len(toks) and toks[i].startswith("-"):
            i += 2 if toks[i] in VALUE_OPTS else 1
        sub = toks[i] if i < len(toks) else ""
        yield here, tuple(toks[1:i]), sub, toks[i + 1:]


def pushes_default(args: list[str]) -> bool:
    """True when a push names the default branch as a destination, or pushes every branch."""
    positional: list[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("--all", "--mirror", "--branches"):
            return True
        if a in PUSH_VALUE_OPTS:
            i += 2
            continue
        if not a.startswith("-"):
            positional.append(a)
        i += 1
    for refspec in positional[1:]:  # the first positional is the remote
        dst = refspec.lstrip("+").split(":")[-1]
        dst = dst.removeprefix("refs/heads/")
        if dst in DEFAULT_BRANCHES:
            return True
    return False


def env_file_reasons(command: str) -> list[str]:
    """Reasons for a command that names the .env file, or asks compose to print its config."""
    out: list[str] = []
    for segment in SEGMENT_SPLIT_RE.split(command):
        try:
            toks = shlex.split(segment)
        except ValueError:
            toks = segment.split()
        words = [os.path.basename(t) for t in _tokens(segment)]
        compose = (words[:1] == ["docker-compose"]) or (words[:1] == ["docker"] and "compose" in words)
        for i, tok in enumerate(toks):
            # Compose reads --env-file for interpolation and prints nothing. Other commands with
            # the same flag (`docker run --env-file .env alpine env`) hand the values to a process
            # that can print them, so the exemption is Compose only (Codex review on #47).
            if compose and (tok.startswith("--env-file=") or (i and toks[i - 1] == "--env-file")):
                continue
            if names_env(tok) and ENV_MSG not in out:
                out.append(ENV_MSG)
        if compose and "config" in words[words.index("compose") + 1 if "compose" in words else 1:]:
            if CONFIG_MSG not in out:
                out.append(CONFIG_MSG)
    return out


def reasons(command: str, cwd: str | None = None,
            branch_of: Callable[[str | None, tuple[str, ...]], str] = current_branch) -> list[str]:
    out = [msg for rx, msg in RULES if rx.search(command)] + env_file_reasons(command)
    for here, git_globals, sub, args in git_calls(command, cwd):
        if sub not in ("commit", "push"):
            continue
        if sub == "push" and pushes_default(args):
            msg = "never push to the default branch; push the issue branch and open a PR"
            if msg not in out:
                out.append(msg)
        branch = branch_of(here, git_globals)
        if branch in DEFAULT_BRANCHES:
            msg = (f"the target repository is on '{branch}'; work on an issue branch, "
                   "never the default")
            if msg not in out:
                out.append(msg)
    return out


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    command = (payload.get("tool_input") or {}).get("command") or ""
    found = reasons(command, payload.get("cwd"))
    if found:
        print("Blocked by .claude/hooks/guard_bash.py: " + "; ".join(found), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
