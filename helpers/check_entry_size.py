#!/usr/bin/env python3
"""check_entry_size: the entry docs and rule files stay small.

- AGENTS.md: at most 200 lines.
- CLAUDE.md: exactly one line, `@AGENTS.md`.
- .agents/rules/*.md: at most 40 lines, 4,000 bytes, and 200 characters per line (one line
  per rule; the story behind a rule goes to .agents/rules/history/).
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    from helpers.govlib import REPO, report
except ModuleNotFoundError:
    from govlib import REPO, report  # type: ignore

NAME = "check_entry_size"
AGENTS_MAX_LINES = 200
RULE_MAX_LINES = 40
RULE_MAX_BYTES = 4000
RULE_MAX_LINE_CHARS = 200


def check(root: Path = REPO) -> list[str]:
    errors = []
    agents = root / "AGENTS.md"
    if not agents.is_file():
        errors.append("AGENTS.md is missing")
    else:
        n = len(agents.read_text(encoding="utf-8").splitlines())
        if n > AGENTS_MAX_LINES:
            errors.append(f"AGENTS.md has {n} lines; the cap is {AGENTS_MAX_LINES}")
    claude = root / "CLAUDE.md"
    if not claude.is_file() or claude.read_text(encoding="utf-8").strip() != "@AGENTS.md":
        errors.append("CLAUDE.md must hold exactly one line: @AGENTS.md")
    for rule in sorted((root / ".agents" / "rules").glob("*.md")):
        text = rule.read_text(encoding="utf-8")
        rel = rule.relative_to(root)
        lines = text.splitlines()
        if len(lines) > RULE_MAX_LINES:
            errors.append(f"{rel} has {len(lines)} lines; the budget is {RULE_MAX_LINES}")
        if len(text.encode("utf-8")) > RULE_MAX_BYTES:
            errors.append(f"{rel} is over {RULE_MAX_BYTES} bytes")
        for i, line in enumerate(lines, 1):
            if len(line) > RULE_MAX_LINE_CHARS:
                errors.append(f"{rel}:{i} is over {RULE_MAX_LINE_CHARS} characters; one short "
                              "line per rule, the story goes to rules/history/")
    return errors


def main() -> int:
    return report(NAME, check())


if __name__ == "__main__":
    sys.exit(main())
