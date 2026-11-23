#!/usr/bin/env python3
"""Append one line to the agent activity log (PLAN section 9).

One JSON line per decision point or external call, in
`.agent-activity-logs/<session>.jsonl` (gitignored):
  {ts, session, role, action, tool, args, result, status}
`args` and `result` are one line each, at most 200 characters, with secrets and home paths
redacted. Standard library only.

    log_agent_action.py --role data-engineer --action decide --tool dbt \
        --args "build --select stg_shop__orders" --result "12 models OK" --status ok
    log_agent_action.py --from-hook      # Claude Code PostToolUse hook; reads JSON on stdin
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_secrets import redact  # noqa: E402

MAX = 200
STATUSES = ("ok", "error", "blocked", "info")


def log_dir() -> Path:
    root = os.environ.get("CLAUDE_PROJECT_DIR") or str(Path(__file__).resolve().parent.parent)
    return Path(root) / ".agent-activity-logs"


def one_line(value) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True)
    text = redact(" ".join(value.split()))
    return text if len(text) <= MAX else text[: MAX - 1] + "…"


def write(entry: dict, directory: Path | None = None) -> Path:
    directory = directory or log_dir()
    directory.mkdir(parents=True, exist_ok=True)
    session = "".join(c for c in str(entry.get("session") or "manual") if c.isalnum() or c in "-_")
    path = directory / f"{session or 'manual'}.jsonl"
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return path


def entry(session, role, action, tool, args, result, status) -> dict:
    return {
        "ts": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "session": session or "manual",
        "role": one_line(role) or "agent",
        "action": one_line(action),
        "tool": one_line(tool),
        "args": one_line(args),
        "result": one_line(result),
        "status": status if status in STATUSES else "info",
    }


def from_hook(payload: dict) -> dict:
    """Summarise a Claude Code hook payload without copying file contents or outputs."""
    tool = payload.get("tool_name") or ""
    tin = payload.get("tool_input") or {}
    resp = payload.get("tool_response")
    cwd = payload.get("cwd") or ""
    if tool == "Bash":
        args = tin.get("command")
    elif "file_path" in tin:
        args = str(tin["file_path"]).replace(cwd.rstrip("/") + "/", "") if cwd else tin["file_path"]
    else:
        args = {k: v for k, v in tin.items() if isinstance(v, (str, int, float, bool))}
    status = "ok"
    result = "done"
    if isinstance(resp, dict):
        if resp.get("is_error") or resp.get("interrupted"):
            status, result = "error", "error or interrupted"
        elif "exit_code" in resp:
            result = f"exit {resp['exit_code']}"
    return entry(payload.get("session_id"), "agent", payload.get("hook_event_name") or "tool",
                 tool, args, result, status)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from-hook", action="store_true")
    ap.add_argument("--session", default=os.environ.get("CLAUDE_SESSION_ID"))
    ap.add_argument("--role", default="agent")
    ap.add_argument("--action", default="")
    ap.add_argument("--tool", default="")
    ap.add_argument("--args", default="")
    ap.add_argument("--result", default="")
    ap.add_argument("--status", default="info", choices=STATUSES)
    args = ap.parse_args(argv)
    try:
        if args.from_hook:
            raw = sys.stdin.read()
            write(from_hook(json.loads(raw) if raw.strip() else {}))
        else:
            write(entry(args.session, args.role, args.action, args.tool, args.args,
                        args.result, args.status))
    except Exception as exc:  # logging must never block the agent
        print(f"log_agent_action: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
