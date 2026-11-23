"""The CI workflows, read statically (S3, security review 2026-11-23)."""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WORKFLOWS = sorted((REPO / ".github" / "workflows").glob("*.yml"))


def test_every_action_is_pinned_to_a_commit_sha():
    """A tag can be moved by the action's owner; a full SHA cannot. The version goes in a comment."""
    assert WORKFLOWS
    for wf in WORKFLOWS:
        for line in wf.read_text(encoding="utf-8").splitlines():
            m = re.match(r"\s*-?\s*uses:\s*(\S+)(.*)$", line)
            if not m or m.group(1).startswith("./"):
                continue
            ref = m.group(1).rpartition("@")[2]
            assert re.fullmatch(r"[0-9a-f]{40}", ref), (wf.name, line.strip())
            assert re.search(r"#\s*v\d", m.group(2)), (wf.name, "version comment missing", line.strip())


def test_workflow_token_is_read_only():
    for wf in WORKFLOWS:
        text = wf.read_text(encoding="utf-8")
        assert re.search(r"^permissions:\n  contents: read$", text, re.M), wf.name
