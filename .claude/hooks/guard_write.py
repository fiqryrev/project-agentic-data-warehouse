#!/usr/bin/env python3
"""PreToolUse hook for Edit, Write, MultiEdit and NotebookEdit.

Blocks writing an env file (other than .env.example) and blocks new text that holds a
secret shape or a home path, using the same patterns as helpers/check_secrets.py.
Exit code 2 blocks the call and shows the reason to the agent. Standard library only.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "helpers"))
from check_secrets import is_env_file, scan_text  # noqa: E402


def new_text(tool_input: dict) -> str:
    parts = [tool_input.get(k) for k in ("content", "new_string", "new_source")]
    for edit in tool_input.get("edits") or []:
        if isinstance(edit, dict):
            parts.append(edit.get("new_string"))
    return "\n".join(p for p in parts if isinstance(p, str))


def reasons(tool_input: dict) -> list[str]:
    out = []
    path = str(tool_input.get("file_path") or tool_input.get("notebook_path") or "")
    if path and is_env_file(path):
        out.append(f"{Path(path).name} holds secrets; the owner edits it by hand")
    findings = scan_text(new_text(tool_input))
    if findings:
        out.append("new text holds a secret or home path (" + ", ".join(findings[:3]) + ")")
    return out


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    found = reasons(payload.get("tool_input") or {})
    if found:
        print("Blocked by .claude/hooks/guard_write.py: " + "; ".join(found), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
