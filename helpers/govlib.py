"""Small shared pieces for the governance checkers (stdlib only)."""
from __future__ import annotations

import json
import os
import re
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
UPDATE_TYPE_RE = re.compile(r"^\s*update-type:\s*(\S+)", re.M)
VERSION_RE = re.compile(r"^\s*dependency-version:\s*(\S+)", re.M)
NAME_RE = re.compile(r"^\s*dependency-name:\s*(\S+)", re.M)
DIGEST_RE = re.compile(r"^(sha256:)?[0-9a-f]{64}$")
# Dependabot's summary lines: "Updates `x` from A to B" (grouped) or "Bumps [x](url) from A to B."
FROM_TO_RE = re.compile(r"^(?:Updates|Bumps) \[?`?([^`\]\s]+)`?\]?(?:\([^)]*\))?"
                        r" from `?([^`\s]+)`? to `?([^`\s]+?)`?\.?$", re.M)
MAJOR_RE = re.compile(r"^v?(\d+)")


def dependabot_messages(base: str, head: str, cwd: Path | None = None) -> list[str] | None:
    """The commit messages of base..head; None when git cannot tell (no history, unknown commits)."""
    try:
        out = subprocess.run(["git", "log", "--format=%B%x1e", f"{base}..{head}"], cwd=cwd or REPO,
                             capture_output=True, text=True, timeout=30, check=True).stdout
    except (subprocess.SubprocessError, OSError):
        return None
    return [m for m in out.split("\x1e") if m.strip()]


def dependabot_entries(message: str) -> list[str]:
    """The entries of the `updated-dependencies` block, one string per `- dependency-name:`."""
    block = message.split("updated-dependencies:", 1)[1]
    return re.split(r"^- (?=dependency-name:)", block, flags=re.M)[1:]


def same_major(old: str, new: str) -> bool:
    """True when both versions start with the same number, a leading `v` dropped."""
    a, b = MAJOR_RE.match(old), MAJOR_RE.match(new)
    return bool(a and b) and a.group(1) == b.group(1)


def dependabot_safe_commit(message: str) -> bool:
    """A commit with Dependabot's metadata in which every dependency is a patch, minor or
    digest-only update. Each entry of a grouped commit qualifies on its own (#72):

    - a non-major `update-type`;
    - a digest as `dependency-version`: an image pinned by digest only has no version to
      compare, so Dependabot writes no `update-type` (#69);
    - no `update-type` (a tag Dependabot cannot read as semver, such as `17.11-alpine` or a
      dropped `v`), and its `from A to B` summary line keeps the same leading major number.

    Anything else (another major, no summary line, no leading number) is not exempt."""
    if "updated-dependencies:" not in message:
        return False
    entries = dependabot_entries(message)
    from_to = {name: (old, new) for name, old, new in FROM_TO_RE.findall(message)}
    for entry in entries:
        types, versions, names = UPDATE_TYPE_RE.findall(entry), VERSION_RE.findall(entry), NAME_RE.findall(entry)
        if types:
            if any(t.endswith("semver-major") for t in types):
                return False
        elif versions and all(DIGEST_RE.match(v) for v in versions):
            continue
        elif not (names and names[0] in from_to and same_major(*from_to[names[0]])):
            return False
    return bool(entries)


def dependabot_pr(event: dict | None = None, cwd: Path | None = None) -> bool:
    """True for a patch, minor or digest-only update Dependabot opened on its own branch. It
    cannot open an issue or write a worknote and a footer, so check_worknote and check_pr_body
    skip it (owner decision, #52); every other check still runs, and the owner reviews and merges.

    Not exempt, so the full checks apply: a major update (security updates ignore the majors
    filter in dependabot.yml, Codex review on #53), and any commit without Dependabot's
    `updated-dependencies` metadata (someone pushed to its branch)."""
    event = pr_event() if event is None else event
    login = ((event.get("user") or {}).get("login") or "")
    ref = ((event.get("head") or {}).get("ref") or "")
    if login != DEPENDABOT or not ref.startswith("dependabot/"):
        return False
    base, head = (event.get("base") or {}).get("sha"), (event.get("head") or {}).get("sha")
    messages = dependabot_messages(base, head, cwd) if base and head else None
    if not messages:
        return False
    return all(dependabot_safe_commit(m) for m in messages)


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
