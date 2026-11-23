"""Small shared pieces for the governance checkers (stdlib only)."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def pr_event() -> dict:
    """The pull_request payload when running in GitHub Actions, else {}."""
    path = os.environ.get("GITHUB_EVENT_PATH")
    if not path or not Path(path).is_file():
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh).get("pull_request") or {}


DEPENDABOT = "dependabot[bot]"


def dependabot_pr(event: dict | None = None) -> bool:
    """True for a pull request Dependabot opened on its own branch. It cannot open an issue or
    write a worknote and a footer, so check_worknote and check_pr_body skip it (owner decision,
    #52); every other check still runs, and the owner reviews and merges it."""
    event = pr_event() if event is None else event
    login = ((event.get("user") or {}).get("login") or "")
    ref = ((event.get("head") or {}).get("ref") or "")
    return login == DEPENDABOT and ref.startswith("dependabot/")


def pr_body(body_file: str | None) -> str | None:
    if body_file:
        return Path(body_file).read_text(encoding="utf-8")
    event = pr_event()
    if event:
        return event.get("body") or ""
    return None


def changed_files(base: str, head: str = "HEAD", cwd: Path | None = None) -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...{head}"],
        cwd=cwd, check=True, capture_output=True, text=True,
    ).stdout
    return [ln for ln in out.splitlines() if ln.strip()]


def tracked_files(cwd: Path = REPO) -> list[str]:
    out = subprocess.run(
        ["git", "ls-files"], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout
    return [ln for ln in out.splitlines() if ln.strip()]


def report(name: str, errors: list[str], warnings: list[str] | None = None) -> int:
    for w in warnings or []:
        print(f"WARNING [{name}] {w}")
    for e in errors:
        print(f"ERROR [{name}] {e}")
    if errors:
        return 1
    print(f"[{name}] OK")
    return 0
