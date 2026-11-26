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


# --- Dependabot PRs (#52; majors stay on the issue path, Codex review on #53) -------------------

MINOR = "Bump x\n\n---\nupdated-dependencies:\n- dependency-name: x\n  update-type: version-update:semver-minor\n...\n"
MAJOR = MINOR.replace("semver-minor", "semver-major")
PATCH_AND_MAJOR = MINOR.replace("- dependency-name: x\n  update-type: version-update:semver-minor\n",
                                "- dependency-name: x\n  update-type: version-update:semver-patch\n"
                                "- dependency-name: y\n  update-type: version-update:semver-major\n")
# #69: an image pinned by digest only has no version to compare, so Dependabot writes no update-type
SHA = "304e0bbeb70a9aa0c40ff26d5a9c0a24296019c6d326ba8b75214fb73441d6e9"
DIGEST = ("Bump x\n\n---\nupdated-dependencies:\n- dependency-name: x\n  dependency-version: " + SHA
          + "\n  dependency-type: direct:production\n  dependency-group: compose-images\n...\n")
DIGEST_AND_TAG = DIGEST.replace("...\n", "- dependency-name: y\n  dependency-version: 2.0.0\n...\n")
# #72: grouped commits; tags Dependabot cannot read as semver come with no update-type
GROUPED = ("Bump the group\n\nUpdates `postgres` from 17.11-alpine to 17.12-alpine\n"
           "Updates `berriai/litellm` from v1.110.2 to 1.111.0\n"
           "Updates `socket-proxy` from 1.13.2 to 1.14.0\n\n---\nupdated-dependencies:\n"
           "- dependency-name: postgres\n  dependency-version: 17.12-alpine\n"
           "- dependency-name: berriai/litellm\n  dependency-version: 1.111.0\n"
           "- dependency-name: socket-proxy\n  dependency-version: 1.14.0\n"
           "  update-type: version-update:semver-minor\n...\n")
UNTYPED_MAJOR = GROUPED.replace("from 17.11-alpine to 17.12-alpine", "from 16.4-alpine to 17.12-alpine")


def dependabot_repo(tmp_path, *messages):
    """A git repository with a base commit and one commit per message; returns (repo, base, head)."""
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    git = lambda *a: subprocess.run(["git", *a], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()  # noqa: E731
    git("init", "-q", "-b", "main")
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "base")
    base = git("rev-parse", "HEAD")
    for m in messages:
        git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", m)
    return repo, base, git("rev-parse", "HEAD")


def event(login, ref, base, head, body=""):
    return {"user": {"login": login}, "head": {"ref": ref, "sha": head}, "base": {"sha": base}, "body": body}


def test_dependabot_pr_needs_its_author_branch_and_non_major_commits(tmp_path):
    from helpers.govlib import dependabot_pr
    repo, base, head = dependabot_repo(tmp_path, MINOR)
    assert dependabot_pr(event("dependabot[bot]", "dependabot/uv/python-1", base, head), repo)
    assert not dependabot_pr(event("dependabot[bot]", "52-dependabot-safe-updates", base, head), repo)
    assert not dependabot_pr(event("someone", "dependabot/uv/python-1", base, head), repo)
    assert not dependabot_pr({}, repo)


def test_dependabot_digest_only_update_is_exempt(tmp_path):
    """#69: digest bumps carry dependency-version digests and no update-type."""
    from helpers.govlib import dependabot_pr
    for i, messages in enumerate(((DIGEST,), (DIGEST.replace(SHA, "sha256:" + SHA),), (DIGEST, MINOR))):
        repo, base, head = dependabot_repo(tmp_path / str(i), *messages)
        assert dependabot_pr(event("dependabot[bot]", "dependabot/docker_compose/infra/x", base, head), repo), messages


def test_dependabot_commit_without_type_or_digest_is_not_exempt(tmp_path):
    """No update-type is only safe when every version is a digest; a pushed commit still blocks."""
    from helpers.govlib import dependabot_pr
    no_versions = "Bump x\n\n---\nupdated-dependencies:\n- dependency-name: x\n...\n"
    short = DIGEST.replace(SHA, SHA[:7])
    bare = "dependency-version: " + SHA + "\n"
    for i, messages in enumerate(((DIGEST_AND_TAG,), (no_versions,), (short,), (bare,), (DIGEST, "docs: worknote"))):
        repo, base, head = dependabot_repo(tmp_path / str(i), *messages)
        assert not dependabot_pr(event("dependabot[bot]", "dependabot/docker_compose/infra/x", base, head), repo), messages


def test_dependabot_grouped_commit_judges_each_entry(tmp_path):
    """#72: an untyped entry passes only on its own same-major summary line, not on its neighbours'."""
    from helpers.govlib import dependabot_pr
    no_summary = GROUPED.replace("Updates `berriai/litellm` from v1.110.2 to 1.111.0\n", "")
    no_number = GROUPED.replace("from 17.11-alpine to 17.12-alpine", "from latest to 17.12-alpine")
    single = ("Bumps [x](https://example.test) from 1.2.3 to 1.3.0.\n\n---\nupdated-dependencies:\n"
              "- dependency-name: x\n  dependency-version: 1.3.0\n...\n")
    cases = (((GROUPED,), True), ((single,), True), ((GROUPED, DIGEST), True),
             ((UNTYPED_MAJOR,), False), ((no_summary,), False), ((no_number,), False), ((GROUPED, MAJOR), False))
    for i, (messages, expected) in enumerate(cases):
        repo, base, head = dependabot_repo(tmp_path / str(i), *messages)
        assert dependabot_pr(event("dependabot[bot]", "dependabot/docker_compose/infra/x", base, head), repo) is expected, i


def test_dependabot_major_or_foreign_commit_is_not_exempt(tmp_path):
    """Security updates ignore the majors filter in dependabot.yml, so the check reads the commits."""
    from helpers.govlib import dependabot_pr
    for i, messages in enumerate(((MAJOR,), (PATCH_AND_MAJOR,), (MINOR, "docs: worknote"), ())):
        repo, base, head = dependabot_repo(tmp_path / str(i), *messages)
        assert not dependabot_pr(event("dependabot[bot]", "dependabot/uv/python-1", base, head), repo), messages
    assert not dependabot_pr(event("dependabot[bot]", "dependabot/uv/python-1", "0" * 40, "1" * 40), tmp_path)


def test_worknote_check_skips_a_minor_dependabot_pr_only(tmp_path, monkeypatch):
    import json

    from helpers import govlib
    for i, (login, messages, expected) in enumerate((("dependabot[bot]", (MINOR,), 0), ("someone", (MINOR,), 1),
                                                     ("dependabot[bot]", (MAJOR,), 1),
                                                     ("dependabot[bot]", (DIGEST,), 0),
                                                     ("dependabot[bot]", (UNTYPED_MAJOR,), 1))):
        repo, base, head = dependabot_repo(tmp_path / str(i), *messages)
        monkeypatch.setattr(govlib, "REPO", repo)
        monkeypatch.chdir(repo)                 # changed_files runs git in the working directory
        path = tmp_path / f"event{i}.json"
        path.write_text(json.dumps({"pull_request": event(login, "dependabot/docker/airflow/x", base, head)}))
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(path))
        assert c.main(["--base", base, "--head", head, "--branch", "dependabot/docker/airflow/x"]) == expected, login
