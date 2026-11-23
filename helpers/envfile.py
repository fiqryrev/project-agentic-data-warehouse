"""envfile: the one reader and writer of `.env` files (M2, review 2026-11-23). Standard library only.

    read_file(path)               the file's keys; a missing file is empty
    read(path)                    the process environment first, then the file (non-empty values)
    write_private(path, text)     owner-only (0600), narrowed before the secrets go in
    set_key(path, key, value)     replace one key's line, or append it

`.env` is gitignored and holds every secret; nothing here prints a value. Callers:
airflow/env_secrets.py (creates and fills it), infra/llm-gateway/bootstrap.py (writes the
virtual keys), llm/observe.py (`read_env`, environment first so the Airflow tasks, which never see
the file, get their keys from compose), llm/gateway_smoke.py.
"""
from __future__ import annotations

import os
from pathlib import Path


def parse(text: str) -> dict[str, str]:
    """`KEY=value` lines; blank lines and `#` comments skipped; whitespace around both trimmed."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            out[key.strip()] = value.strip()
    return out


def read_file(path: Path) -> dict[str, str]:
    return parse(path.read_text(encoding="utf-8")) if path.exists() else {}


def read(path: Path = Path(".env")) -> dict[str, str]:
    """The file's keys, overridden by non-empty process environment variables. Compose passes
    `${KEY:-}` (empty) when `.env` lacks a key, so an empty variable never hides the file."""
    return {**read_file(path), **{k: v for k, v in os.environ.items() if v}}


def write_private(path: Path, text: str) -> None:
    """Write `text` readable by the owner only (0600), also when the file already exists: an
    existing file keeps its mode on open, so it is narrowed before anything is written."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)


def set_key(path: Path, key: str, value: str) -> None:
    """Replace the line that sets `key`, or append one; every other line stays as it was."""
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    for i, line in enumerate(lines):
        if line.split("=", 1)[0].strip() == key:
            lines[i] = f"{key}={value}"
            break
    else:
        lines.append(f"{key}={value}")
    write_private(path, "\n".join(lines) + "\n")
