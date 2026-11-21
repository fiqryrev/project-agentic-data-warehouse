"""check_secrets: secret shapes, home paths and tracked env files fail."""
from helpers import check_secrets as c

# Built at run time so this file itself holds no secret shape or home path.
HOME = "/" + "Users" + "/somebody/project/file.py"
KEYS = [
    "sk-" + "ant-" + "a" * 30,
    "nv" + "api-" + "b" * 30,
    "gh" + "p_" + "c" * 36,
    "AK" + "IA" + "ABCDEFGHIJKLMNOP",
    "sk-" + "or-v1-" + "d" * 40,
]


def test_home_path_found():
    assert c.scan_text(f"open('{HOME}')") == ["line 1: home path"]


def test_placeholders_pass():
    assert c.scan_text("/" + "Users/<you>/x and /" + "home/runner/work and $HOME/x") == []


def test_each_key_shape_found():
    for key in KEYS:
        assert c.scan_text(f"KEY={key}"), key


def test_clean_text_passes():
    assert c.scan_text("NVIDIA_API_KEY=\nOPENROUTER_API_KEY=<set in .env>") == []


def test_redact():
    out = c.redact(f"{HOME} {KEYS[0]}")
    assert "somebody" not in out and KEYS[0] not in out and "[REDACTED]" in out


def test_env_file_tracked_fails(tmp_path):
    (tmp_path / ".env").write_text("X=1\n")
    (tmp_path / ".env.example").write_text("X=\n")
    errors = c.check([".env", ".env.example", "infra/.env.local"], root=tmp_path)
    assert len(errors) == 2 and all("env file is tracked" in e for e in errors)


def test_file_with_secret_fails(tmp_path):
    (tmp_path / "a.py").write_text(f"x = '{KEYS[1]}'\n")
    assert c.check(["a.py"], root=tmp_path) == ["a.py: line 1: NVIDIA key"]


def test_repository_is_clean():
    assert c.check(c.tracked_files()) == []
