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


def test_dependabot_proposes_patch_and_minor_only():
    """#52: a major version is a planned change; DuckDB moves only with infra/duckdb-pins.yaml."""
    import yaml
    cfg = yaml.safe_load((REPO / ".github" / "dependabot.yml").read_text(encoding="utf-8"))
    ecosystems = {u["package-ecosystem"] for u in cfg["updates"]}
    assert ecosystems == {"uv", "docker", "docker-compose", "github-actions"}
    for u in cfg["updates"]:
        ignores = u.get("ignore") or []
        assert {"dependency-name": "*", "update-types": ["version-update:semver-major"]} in ignores, u["package-ecosystem"]
        if u["package-ecosystem"] == "uv":
            assert {"dependency-name": "duckdb", "update-types": ["version-update:semver-minor"]} in ignores
    pins = yaml.safe_load((REPO / "infra" / "duckdb-pins.yaml").read_text(encoding="utf-8"))
    assert pins["loader"].endswith(",<1.6")        # the minor ignore above is what keeps this true
