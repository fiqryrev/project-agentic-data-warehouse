#!/usr/bin/env python3
"""PreToolUse hook for Bash: block the commands the hard rules forbid.

- merging a PR (never merge unless the owner names the PR; the owner runs it);
- committing or pushing while the target repository is on the default branch, pushing to
  the default branch, or pushing every branch at once;
- printing the .env file.

The target repository is the one Git itself would pick: the hook follows `cd <dir>` inside
the command and Git's global options (`-C <dir>`, `--git-dir`, `--work-tree`), so
`git -C <main checkout> commit` is checked against that checkout's branch, not the
session's. Exit code 2 blocks the call and shows the reason to the agent. Standard library
only.
"""
from __future__ import annotations

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
    (re.compile(r"\b(?:cat|less|more|head|tail|bat|nl|strings)\b[^;&|\n]*\s\.env(?:\s|$)"),
     "never print .env; it holds secrets"),
]
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


def reasons(command: str, cwd: str | None = None,
            branch_of: Callable[[str | None, tuple[str, ...]], str] = current_branch) -> list[str]:
    out = [msg for rx, msg in RULES if rx.search(command)]
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
