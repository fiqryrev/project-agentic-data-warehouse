"""Create .env from .env.example and fill each empty *_SECRET with a random value.

    uv run python airflow/env_secrets.py .env .env.example

Keys already set in .env are kept; keys new in .env.example are added. Prints key names only,
never values. .env is gitignored and written 0600 (owner only).
"""
from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path


def parse(text: str) -> dict[str, str]:
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            out[key.strip()] = value.strip()
    return out


def write_private(path: Path, text: str) -> None:
    """Write `text` readable by the owner only (0600), also when the file already exists."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)                # an existing file keeps its mode on open; narrow it first
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)


def fill(env: Path, example: Path) -> list[str]:
    """Write env; return the keys that were added or given a secret."""
    current = parse(env.read_text(encoding="utf-8")) if env.exists() else {}
    lines = env.read_text(encoding="utf-8").splitlines() if env.exists() else []
    changed = []
    for key, default in parse(example.read_text(encoding="utf-8")).items():
        if key not in current:
            value = secrets.token_hex(32) if key.endswith("_SECRET") and not default else default
            lines.append(f"{key}={value}")
            changed.append(key)
        elif key.endswith("_SECRET") and not current[key]:
            lines = [f"{key}={secrets.token_hex(32)}" if ln.strip().startswith(f"{key}=") else ln
                     for ln in lines]
            changed.append(key)
    write_private(env, "\n".join(lines) + "\n")
    return changed


if __name__ == "__main__":
    env, example = (Path(a) for a in sys.argv[1:3])
    keys = fill(env, example)
    print(f"[env_secrets] {env}: " + (f"set {', '.join(keys)}" if keys else "up to date"))
