"""check_worknote: a PR without its issue's worknote fails."""
import os
import subprocess
import sys
from pathlib import Path

from helpers import check_worknote as c

REPO = Path(__file__).resolve().parents[2]


def test_issue_from_body_wins_over_branch():
    assert c.issue_number("Closes #12", "7-other") == 12
    assert c.issue_number("fixes #3 and more", None) == 3


def test_issue_from_branch():
    assert c.issue_number("", "7-generator-daily") == 7
    assert c.issue_number(None, "someone/9-loader") == 9
    assert c.issue_number("no ref", "feature-x") is None


def test_pr_with_worknote_passes():
    assert c.check(["helpers/x.py", "docs/task-management/12-thing.md"], 12) == []


def test_pr_without_worknote_fails():
    errors = c.check(["helpers/x.py", "README.md"], 12)
    assert errors and "does not touch a worknote for issue #12" in errors[0]


def test_worknote_of_another_issue_fails():
    assert c.check(["docs/task-management/11-old.md"], 12)


def test_pr_without_issue_fails():
    assert "cannot tell the issue" in c.check(["docs/task-management/12-x.md"], None)[0]


def _git(cwd, *args):
    subprocess.run(["git", "-c", "commit.gpgsign=false", *args], cwd=cwd, check=True, capture_output=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"})


def test_cli_on_a_real_branch_without_worknote(tmp_path):
    """End to end, as CI runs it: a branch that changes code but no worknote fails."""
    _git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "a.txt").write_text("a\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "base")
    _git(tmp_path, "checkout", "-qb", "12-thing")
    (tmp_path / "b.txt").write_text("b\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "work")
    body = tmp_path / "body.md"
    body.write_text("Closes #12\n")
    script = REPO / "helpers" / "check_worknote.py"
    run = subprocess.run([sys.executable, str(script), "--base", "main", "--body-file", str(body)],
                         cwd=tmp_path, capture_output=True, text=True)
    assert run.returncode == 1, run.stdout + run.stderr
    assert "does not touch a worknote for issue #12" in run.stdout
    note = tmp_path / "docs" / "task-management" / "12-thing.md"
    note.parent.mkdir(parents=True)
    note.write_text("# 12\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "worknote")
    run = subprocess.run([sys.executable, str(script), "--base", "main", "--body-file", str(body)],
                         cwd=tmp_path, capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
