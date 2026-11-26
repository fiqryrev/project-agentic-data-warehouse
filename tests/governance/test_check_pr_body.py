"""check_pr_body: the deliberately bad fixtures fail, the good one passes."""
import subprocess
import sys
from pathlib import Path

import pytest

from helpers import check_pr_body as c

FIX = Path(__file__).parent / "fixtures" / "pr_bodies"
REPO = Path(__file__).resolve().parents[2]


def body(name):
    return (FIX / name).read_text(encoding="utf-8")


def test_good_body_passes():
    assert c.check(body("good.md")) == []


@pytest.mark.parametrize("name, needle", [
    ("bad_untokened.md", "has no result token"),
    ("bad_no_footer.md", "missing the '## AI usage' footer"),
    ("bad_watermark.md", "tool watermark"),
    ("bad_footer_shape.md", "exactly six lines"),
    ("bad_no_sections.md", "missing '## Pre-merge' section"),
])
def test_bad_bodies_fail(name, needle):
    errors = c.check(body(name))
    assert any(needle in e for e in errors), errors


@pytest.mark.parametrize("name", ["bad_untokened.md", "bad_no_footer.md"])
def test_cli_exits_non_zero_on_bad_body(name):
    """What CI runs: the step fails, so the PR is blocked."""
    run = subprocess.run([sys.executable, "-m", "helpers.check_pr_body", "--body-file",
                          str(FIX / name)], cwd=REPO, capture_output=True, text=True)
    assert run.returncode == 1 and "ERROR [check_pr_body]" in run.stdout


def test_fail_token_blocks():
    errors = c.check(body("good.md").replace("pytest -q` → PASS", "pytest -q` → FAIL: 2 tests red"))
    assert any("reports FAIL" in e for e in errors)


def test_skip_needs_rule_and_reason():
    errors = c.check(body("good.md").replace("SKIP[no-network]: ran in CI only", "SKIP"))
    assert any("has no result token" in e for e in errors)


def test_footer_arithmetic_is_checked():
    bad = body("good.md").replace("Total Token: 1,100", "Total Token: 1,200")
    assert any("input plus output" in e for e in c.check(bad))


def test_output_cache_hit_must_be_zero():
    bad = body("good.md").replace("Output Token Usage: 100 ($0.00) - Cache hit (0, $0.00)",
                                  "Output Token Usage: 100 ($0.00) - Cache hit (5, $0.00)")
    assert any("never cached" in e for e in c.check(bad))


def test_text_after_footer_fails():
    assert any("must end the body" in e for e in c.check(body("good.md") + "\nmore text\n"))


def test_model_line_needs_effort():
    bad = body("good.md").replace("claude-haiku-5-5 (effort low)", "claude-haiku-5-5")
    assert any("Model Name" in e for e in c.check(bad))


def test_pr_body_check_skips_a_minor_dependabot_pr_only(tmp_path, monkeypatch):
    """#52: Dependabot cannot write the sections or the footer; a person's body, the bot on another
    branch and a major update (Codex review on #53) are still checked."""
    import json

    from helpers import govlib
    from tests.governance.test_check_worknote import DIGEST, MAJOR, MINOR, dependabot_repo, event
    cases = (("dependabot[bot]", "dependabot/uv/python-1", MINOR, 0), ("someone", "dependabot/uv/python-1", MINOR, 1),
             ("dependabot[bot]", "7-feature", MINOR, 1), ("dependabot[bot]", "dependabot/uv/python-1", MAJOR, 1),
             ("dependabot[bot]", "dependabot/docker_compose/infra/x", DIGEST, 0))
    for i, (login, ref, message, expected) in enumerate(cases):
        repo, base, head = dependabot_repo(tmp_path / str(i), message)
        monkeypatch.setattr(govlib, "REPO", repo)
        path = tmp_path / f"event{i}.json"
        path.write_text(json.dumps({"pull_request": event(login, ref, base, head, "Bumps duckdb.")}))
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(path))
        assert c.main([]) == expected, (login, ref, message[-40:])
