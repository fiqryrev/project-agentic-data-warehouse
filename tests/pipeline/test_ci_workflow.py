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


def test_makefile_checks_and_ci_run_the_same_checkers():
    """M3: the checkers are listed by hand twice (one CI step each, so a failure names its
    checker); this keeps the two lists equal. check_worknote and check_pr_body run in CI only."""
    makefile = (REPO / "Makefile").read_text(encoding="utf-8")
    block = makefile.split("\nchecks:\n", 1)[1].split("\n\n", 1)[0]
    in_make = re.findall(r"uv run python -m helpers\.(check_\w+)", block)
    ci = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    in_ci = [c for c in re.findall(r"uv run python -m helpers\.(check_\w+)", ci)
             if c not in ("check_worknote", "check_pr_body")]
    assert in_make and in_make == in_ci, (in_make, in_ci)


def test_runtime_dependencies_have_a_major_upper_bound():
    """M4: uv.lock pins installs; the bounds keep a re-lock from crossing a major version."""
    import tomllib
    project = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["version"] != "0.0.0"
    for dep in project["dependencies"]:
        assert "<" in dep, dep
