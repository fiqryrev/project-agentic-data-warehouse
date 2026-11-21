#!/usr/bin/env python3
"""PreToolUse hook for Bash: block the commands the hard rules forbid.

- merging a PR (never merge unless the owner names the PR; the owner runs it);
- committing or pushing while on the default branch, pushing to it, or force-pushing it;
- printing the .env file.
Exit code 2 blocks the call and shows the reason to the agent. Standard library only.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys

DEFAULT_BRANCHES = ("main", "master")
RULES = [
    (re.compile(r"\bgh\s+pr\s+merge\b"),
     "never merge: only the owner merges, and only a PR they name"),
    (re.compile(r"\bgit\s+push\b[^;&|]*\s(?:\S*:)?(?:refs/heads/)?(?:main|master)(?=[\s;&|]|$)"),
     "never push to the default branch; push the issue branch and open a PR"),
    (re.compile(r"\bgit\s+push\b[^;&|]*\s(?:--force(?!-with-lease)|-f)\b[^;&|]*\s(?:\S*:)?(?:main|master)(?=[\s;&|]|$)"),
     "never force-push the default branch"),
    (re.compile(r"\b(?:cat|less|more|head|tail|bat|nl|strings)\b[^;&|]*\s\.env(?:\s|$)"),
     "never print .env; it holds secrets"),
]


def current_branch(cwd: str | None) -> str:
    try:
        return subprocess.run(["git", "branch", "--show-current"], cwd=cwd or None,
                              capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception:
        return ""


def reasons(command: str, branch: str) -> list[str]:
    out = [msg for rx, msg in RULES if rx.search(command)]
    if branch in DEFAULT_BRANCHES and re.search(r"\bgit\s+(?:commit|push)\b", command):
        out.append(f"you are on '{branch}'; work on an issue branch, never the default")
    return out


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    command = (payload.get("tool_input") or {}).get("command") or ""
    found = reasons(command, current_branch(payload.get("cwd")))
    if found:
        print("Blocked by .claude/hooks/guard_bash.py: " + "; ".join(found), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
