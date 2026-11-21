"""check_entry_size: AGENTS.md cap, CLAUDE.md shape and rule-file budget."""
from helpers import check_entry_size as c


def make(tmp_path, agents_lines=10, claude="@AGENTS.md\n", rule="1. one rule\n"):
    (tmp_path / "AGENTS.md").write_text("x\n" * agents_lines)
    (tmp_path / "CLAUDE.md").write_text(claude)
    rules = tmp_path / ".agents" / "rules"
    rules.mkdir(parents=True)
    (rules / "core.md").write_text(rule)
    return tmp_path


def test_repo_passes():
    assert c.check() == []


def test_small_passes(tmp_path):
    assert c.check(make(tmp_path)) == []


def test_agents_over_cap_fails(tmp_path):
    assert "201 lines" in c.check(make(tmp_path, agents_lines=201))[0]


def test_claude_md_must_only_import(tmp_path):
    assert "CLAUDE.md" in c.check(make(tmp_path, claude="@AGENTS.md\nextra\n"))[0]


def test_rule_file_budget(tmp_path):
    errors = c.check(make(tmp_path, rule="r\n" * 41 + "y" * 201 + "\n"))
    assert any("41" in e or "42" in e for e in errors)
    assert any("characters" in e for e in errors)
