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


def fake_branches(mapping, default="7-x"):
    """branch_of stub: the branch depends on the directory and the -C/--git-dir options."""
    def branch_of(cwd, git_globals):
        key = cwd
        for i, opt in enumerate(git_globals):
            if opt in ("-C", "--git-dir", "--work-tree") and i + 1 < len(git_globals):
                key = git_globals[i + 1]
            elif opt.startswith(("--git-dir=", "--work-tree=")):
                key = opt.split("=", 1)[1]
        return mapping.get(key, default)
    return branch_of


ON_ISSUE = fake_branches({})
ON_MAIN = fake_branches({}, default="main")


def test_bash_guard_blocks_merge_and_default_branch():
    assert guard_bash.reasons("gh pr merge 5 --squash", "/wt", ON_ISSUE)
    assert guard_bash.reasons("gh -R a/b pr merge 5", "/wt", ON_ISSUE)
    assert guard_bash.reasons("git push origin main", "/wt", ON_ISSUE)
    assert guard_bash.reasons("git push origin HEAD:main", "/wt", ON_ISSUE)
    assert guard_bash.reasons("git push origin +HEAD:refs/heads/master", "/wt", ON_ISSUE)
    assert guard_bash.reasons("git push --all origin", "/wt", ON_ISSUE)
    assert guard_bash.reasons("cat .env", "/wt", ON_ISSUE)
    assert guard_bash.reasons("git commit -m x", "/wt", ON_MAIN)


def test_bash_guard_follows_git_target_repository():
    """Codex review on PR #5: `git -C <main checkout> commit` from an issue worktree."""
    branches = fake_branches({"/repo": "main", "../repo": "main", "/repo/.git": "main"})
    for cmd in [
        "git -C /repo commit -m x",
        "git -c user.name=x -C /repo commit -m x",
        "git --git-dir=/repo/.git commit -m x",
        "git --work-tree /repo commit -m x",
        "cd /repo && git commit -m x",
        "git status; cd /repo && GIT_EDITOR=true git commit",
        "git -C /repo push",
        "git -C /repo push origin HEAD",
    ]:
        assert guard_bash.reasons(cmd, "/wt", branches), cmd
    assert guard_bash.reasons("git -C /wt commit -m x", "/wt", branches) == []
    assert guard_bash.reasons("git -C /repo status", "/wt", branches) == []


def test_bash_guard_reads_the_real_branch_of_c_target(tmp_path):
    """End to end with real git: the hook resolves -C itself."""
    import subprocess as sp
    main_repo, wt = tmp_path / "repo", tmp_path / "wt"
    for d, b in ((main_repo, "main"), (wt, "7-x")):
        d.mkdir()
        sp.run(["git", "init", "-q", "-b", b], cwd=d, check=True)
    assert guard_bash.reasons(f"git -C {main_repo} commit -m x", str(wt))
    assert guard_bash.reasons(f"cd {main_repo} && git commit -m x", str(wt))
    assert guard_bash.reasons("git commit -m x", str(wt)) == []


def test_bash_guard_allows_normal_work():
    assert guard_bash.reasons("git push -u origin 7-main-loader", "/wt", ON_ISSUE) == []
    assert guard_bash.reasons("git push -o ci.skip origin 7-x", "/wt", ON_ISSUE) == []
    assert guard_bash.reasons("git commit -m 'fix main page'", "/wt", ON_ISSUE) == []
    assert guard_bash.reasons("cat .env.example", "/wt", ON_ISSUE) == []
    assert guard_bash.reasons("uv run pytest -q", "/wt", ON_MAIN) == []
    assert guard_bash.reasons("git log main..HEAD", "/wt", ON_MAIN) == []


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


ENV_READS = [
    "cat .env", "grep KEY .env", "awk -F= '{print $2}' .env", "sed -n p .env", "source .env", ". .env",
    "cp .env /tmp/x", "python3 -c 'import sys; print(sys.stdin.read())' < .env", "cat<.env",
    "echo $(<.env)", "cat ./.env", "cat ../repo/.env", "git status && grep -c = .env",
]
COMPOSE_CONFIG = [
    "docker compose -f infra/compose.yml config",
    "docker compose -f infra/compose.yml --env-file .env --profile core config",
    "docker-compose config", "env X=1 docker compose config",
]
ALLOWED = [
    "cat .env.example", "grep -n SECRET .env.example", "grep -n FOO .envrc",
    "docker compose -f infra/compose.yml --env-file .env --profile core up -d --build --wait",
    "docker compose -f infra/compose.yml --env-file .env --profile core exec airflow-scheduler bash x.sh",
    "docker compose --env-file=.env ps", "make up-core", "make backfill FROM=2026-01-01 TO=2026-01-02",
    "git config user.name", "docker config ls", "uv run pytest -q",
]


def test_bash_guard_blocks_every_way_to_read_dot_env():
    """S10 (security review 2026-11-23): naming the file is enough, whatever the command."""
    for cmd in ENV_READS:
        assert guard_bash.ENV_MSG in guard_bash.reasons(cmd, "/wt", ON_ISSUE), cmd
    for cmd in COMPOSE_CONFIG:
        assert guard_bash.CONFIG_MSG in guard_bash.reasons(cmd, "/wt", ON_ISSUE), cmd


def test_bash_guard_allows_env_example_and_compose_env_file():
    for cmd in ALLOWED:
        assert guard_bash.reasons(cmd, "/wt", ON_ISSUE) == [], cmd


def test_make_targets_that_pass_the_env_file_stay_allowed():
    """The Makefile's compose lines (`--env-file .env`) must pass the guard as written there."""
    import re
    text = (REPO / "Makefile").read_text(encoding="utf-8")
    lines = [ln.strip() for ln in text.splitlines() if re.match(r"^[A-Z]+ = docker compose", ln)]
    assert lines
    for ln in lines:
        cmd = ln.split("=", 1)[1].strip() + " up -d"
        assert guard_bash.reasons(cmd, "/wt", ON_ISSUE) == [], cmd


def test_bash_guard_blocks_dot_env_from_the_hook_process():
    run = run_hook(REPO / ".claude/hooks/guard_bash.py",
                   {"tool_input": {"command": "grep SECRET .env"}, "cwd": str(REPO)})
    assert run.returncode == 2 and ".env" in run.stderr
