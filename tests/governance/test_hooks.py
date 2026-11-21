"""The three Claude Code hooks: two guards and the activity log."""
import json
import subprocess
import sys
from pathlib import Path

from helpers import log_agent_action as log

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / ".claude" / "hooks"))
import guard_bash  # noqa: E402
import guard_write  # noqa: E402

HOME = "/" + "Users" + "/somebody/x"


def run_hook(script, payload):
    return subprocess.run([sys.executable, str(script)], input=json.dumps(payload),
                          capture_output=True, text=True)


def test_bash_guard_blocks_merge_and_default_branch():
    assert guard_bash.reasons("gh pr merge 5 --squash", "7-x")
    assert guard_bash.reasons("git push origin main", "7-x")
    assert guard_bash.reasons("git push origin HEAD:main", "7-x")
    assert guard_bash.reasons("cat .env", "7-x")
    assert guard_bash.reasons("git commit -m x", "main")


def test_bash_guard_allows_normal_work():
    assert guard_bash.reasons("git push -u origin 7-main-loader", "7-main-loader") == []
    assert guard_bash.reasons("git commit -m 'x'", "7-x") == []
    assert guard_bash.reasons("cat .env.example", "7-x") == []
    assert guard_bash.reasons("uv run pytest -q", "main") == []


def test_bash_guard_exit_code_blocks():
    run = run_hook(REPO / ".claude/hooks/guard_bash.py",
                   {"tool_input": {"command": "gh pr merge 3"}, "cwd": str(REPO)})
    assert run.returncode == 2 and "never merge" in run.stderr


def test_write_guard():
    assert guard_write.reasons({"file_path": "/repo/.env", "content": "X=1"})
    assert guard_write.reasons({"file_path": "/repo/a.md", "content": f"see {HOME}/y"})
    assert guard_write.reasons({"file_path": "a.md", "edits": [{"new_string": "nv" + "api-" + "z" * 30}]})
    assert guard_write.reasons({"file_path": "/repo/.env.example", "content": "X="}) == []
    run = run_hook(REPO / ".claude/hooks/guard_write.py",
                   {"tool_input": {"file_path": "x/.env", "content": ""}})
    assert run.returncode == 2


def test_activity_log_line(tmp_path):
    e = log.entry("s-1", "data-engineer", "call", "dbt", "build\n--select  x " + HOME,
                  "ok " * 200, "ok")
    path = log.write(e, tmp_path)
    rec = json.loads(path.read_text().splitlines()[0])
    assert path.name == "s-1.jsonl"
    assert set(rec) == {"ts", "session", "role", "action", "tool", "args", "result", "status"}
    assert "\n" not in rec["args"] and "somebody" not in rec["args"]
    assert len(rec["result"]) <= 200


def test_activity_log_from_hook(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    payload = {"session_id": "abc", "hook_event_name": "PostToolUse", "tool_name": "Bash",
               "tool_input": {"command": "git status"}, "tool_response": {"exit_code": 0}}
    run = subprocess.run([sys.executable, str(REPO / "helpers/log_agent_action.py"), "--from-hook"],
                         input=json.dumps(payload), capture_output=True, text=True,
                         env={**__import__("os").environ, "CLAUDE_PROJECT_DIR": str(tmp_path)})
    assert run.returncode == 0
    rec = json.loads((tmp_path / ".agent-activity-logs" / "abc.jsonl").read_text())
    assert rec["tool"] == "Bash" and rec["args"] == "git status" and rec["status"] == "ok"
