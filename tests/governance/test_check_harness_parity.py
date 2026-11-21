"""check_harness_parity: every registered tool declares the six duties and reaches every skill."""
import shutil
from pathlib import Path

import yaml

from helpers import check_harness_parity as c

REPO = Path(__file__).resolve().parents[2]


def copy_repo(tmp_path):
    for name in ("AGENTS.md", "CLAUDE.md", "helpers"):
        src = REPO / name
        (shutil.copytree if src.is_dir() else shutil.copy)(src, tmp_path / name)
    shutil.copytree(REPO / ".agents", tmp_path / ".agents", symlinks=True)
    shutil.copytree(REPO / ".claude", tmp_path / ".claude", symlinks=True,
                    ignore=shutil.ignore_patterns("worktrees", "settings.local.json"))
    return tmp_path


def edit_registry(root, fn):
    path = root / ".agents" / "harnesses.yaml"
    reg = yaml.safe_load(path.read_text())
    fn(reg)
    path.write_text(yaml.safe_dump(reg))


def test_repo_passes():
    assert c.check() == []


def test_missing_duty_fails(tmp_path):
    root = copy_repo(tmp_path)
    edit_registry(root, lambda r: r["harnesses"]["claude-code"].pop("mcp"))
    assert "claude-code: duty 'mcp' is not declared" in c.check(root)


def test_none_needs_reason(tmp_path):
    root = copy_repo(tmp_path)
    edit_registry(root, lambda r: r["harnesses"]["claude-code"].update(mcp={"none": ""}))
    assert any("needs a reason" in e for e in c.check(root))


def test_duty_list_must_be_the_six(tmp_path):
    root = copy_repo(tmp_path)
    edit_registry(root, lambda r: r.update(duties=["entry", "rules"]))
    assert any(e.startswith("duties must be") for e in c.check(root))


def test_unreachable_skill_fails(tmp_path):
    root = copy_repo(tmp_path)
    (root / ".claude" / "skills").unlink()
    (root / ".claude" / "skills").mkdir()
    errors = c.check(root)
    assert any("skill 'pr-open' is not reachable" in e for e in errors)


def test_second_tool_must_declare_everything(tmp_path):
    root = copy_repo(tmp_path)
    edit_registry(root, lambda r: r["harnesses"].update(other={"name": "Other", "entry": {"none": "x"}}))
    errors = c.check(root)
    assert "other: duty 'skills' is not declared" in errors


def test_unwired_hook_fails(tmp_path):
    root = copy_repo(tmp_path)
    settings = root / ".claude" / "settings.json"
    settings.write_text(settings.read_text().replace("guard_write.py", "something_else.py"))
    assert any("guard_write.py is not wired" in e for e in c.check(root))
