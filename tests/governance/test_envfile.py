"""helpers/envfile.py: the one reader and writer of .env files (M2, review 2026-11-23)."""
from pathlib import Path

from helpers import envfile

REPO = Path(__file__).resolve().parents[2]


def test_parse_skips_comments_and_blank_lines_and_trims():
    text = "# c\n\n  A_SECRET = x \nB=\nnot a pair\nC=a=b\n"
    assert envfile.parse(text) == {"A_SECRET": "x", "B": "", "C": "a=b"}


def test_read_file_and_missing_file(tmp_path):
    f = tmp_path / ".env"
    f.write_text("A=1\n")
    assert envfile.read_file(f) == {"A": "1"} and envfile.read_file(tmp_path / "none") == {}


def test_read_prefers_non_empty_environment(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_text("A_SECRET=file\nB_SECRET=file-b\n")
    monkeypatch.setenv("A_SECRET", "env")
    monkeypatch.setenv("B_SECRET", "")                     # compose's ${KEY:-} never hides the file
    env = envfile.read(f)
    assert env["A_SECRET"] == "env" and env["B_SECRET"] == "file-b"


def test_write_private_narrows_an_existing_file(tmp_path):
    f = tmp_path / ".env"
    f.write_text("old\n")
    f.chmod(0o644)
    envfile.write_private(f, "A=1\n")
    assert f.stat().st_mode & 0o777 == 0o600 and f.read_text() == "A=1\n"


def test_set_key_replaces_or_appends_and_keeps_other_lines(tmp_path):
    f = tmp_path / ".env"
    f.write_text("# keep\nA=1\nB=2\n")
    envfile.set_key(f, "A", "9")
    envfile.set_key(f, "C", "3")
    assert f.read_text() == "# keep\nA=9\nB=2\nC=3\n" and f.stat().st_mode & 0o777 == 0o600


def test_no_second_env_parser_or_writer():
    """The four former copies now call envfile; a new copy fails here."""
    for path in [*REPO.glob("airflow/**/*.py"), *REPO.glob("llm/*.py"), *REPO.glob("infra/**/*.py"),
                 *REPO.glob("publish/*.py"), *REPO.glob("helpers/*.py")]:
        if "upstream" in path.parts or path.name == "envfile.py":
            continue
        text = path.read_text(encoding="utf-8")
        assert "os.fchmod" not in text and "O_CREAT" not in text, path.relative_to(REPO)
        assert 'line.partition("=")' not in text, path.relative_to(REPO)
