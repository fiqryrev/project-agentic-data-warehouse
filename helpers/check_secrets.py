#!/usr/bin/env python3
"""check_secrets: no secrets, no home paths and no tracked `.env` file.

Scans every tracked text file (or the paths given). gitleaks runs beside it in CI; this
check adds the home-path rule and the provider key shapes this project uses. Standard
library only, because the write hook imports it too.

Usage: check_secrets.py [PATH ...]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    from helpers.govlib import REPO, report, tracked_files
except ModuleNotFoundError:
    from govlib import REPO, report, tracked_files  # type: ignore

NAME = "check_secrets"

# A home folder followed by a real account name. Placeholders such as <user> or $USER do
# not match, and neither does the GitHub runner's own home.
HOME_PATH_RE = re.compile(
    r"(?:/(?:Users|home)/(?!runner/)[A-Za-z0-9._-]+/|[A-Za-z]:\\Users\\[A-Za-z0-9._-]+)"
)
SECRET_RES = {
    "Anthropic key": re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"),
    "OpenRouter key": re.compile(r"sk-or-v1-[A-Za-z0-9]{20,}"),
    "OpenAI-style key": re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{32,}"),
    "NVIDIA key": re.compile(r"nvapi-[A-Za-z0-9_-]{20,}"),
    "Langfuse key": re.compile(r"\b[ps]k-lf-[0-9a-f-]{20,}"),
    "GitHub token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})"),
    "Hugging Face token": re.compile(r"\bhf_[A-Za-z0-9]{30,}"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "Slack token": re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    "private key": re.compile(r"-----BEGIN (?:[A-Z]+ )*PRIVATE KEY-----"),
}
ENV_FILE_RE = re.compile(r"(?:^|/)\.env(?:\.[^/]+)?$")
ENV_OK = {".env.example"}


def scan_text(text: str) -> list[str]:
    """Return one finding per line that holds a home path or a secret shape."""
    findings = []
    for n, line in enumerate(text.splitlines(), 1):
        if HOME_PATH_RE.search(line):
            findings.append(f"line {n}: home path")
        for label, rx in SECRET_RES.items():
            if rx.search(line):
                findings.append(f"line {n}: {label}")
    return findings


def redact(text: str) -> str:
    text = HOME_PATH_RE.sub("~/", text)
    for rx in SECRET_RES.values():
        text = rx.sub("[REDACTED]", text)
    return text


def is_env_file(path: str) -> bool:
    return bool(ENV_FILE_RE.search(path)) and Path(path).name not in ENV_OK


def check(paths: list[str], root: Path = REPO) -> list[str]:
    errors = []
    for rel in paths:
        if is_env_file(rel):
            errors.append(f"{rel}: env file is tracked; keep secrets in the gitignored .env")
            continue
        p = root / rel
        if not p.is_file() or p.is_symlink():
            continue
        data = p.read_bytes()
        if b"\0" in data[:8192]:
            continue
        for finding in scan_text(data.decode("utf-8", errors="replace")):
            errors.append(f"{rel}: {finding}")
    return errors


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    return report(NAME, check(argv or tracked_files()))


if __name__ == "__main__":
    sys.exit(main())
