#!/usr/bin/env python3
"""check_worknote: a PR touches the worknote of its issue.

The issue number comes from the PR body (`Closes #N`, `Fixes #N`, `Resolves #N`, `Refs #N`)
or from a branch named `<issue>-<slug>`. The PR must add or change
`docs/task-management/<issue>-<slug>.md`.

Usage: check_worknote.py --base <ref> [--head <ref>] [--branch <name>] [--body-file FILE]
"""
from __future__ import annotations

import argparse
import os
import re
import sys

try:
    from helpers.govlib import changed_files, dependabot_pr, pr_body, report
except ModuleNotFoundError:
    from govlib import changed_files, dependabot_pr, pr_body, report  # type: ignore

NAME = "check_worknote"
WORKNOTE_DIR = "docs/task-management"
BODY_ISSUE_RE = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?|refs?)\s+#(\d+)\b", re.I)
BRANCH_ISSUE_RE = re.compile(r"(?:^|/)(\d+)-[A-Za-z0-9]")


def issue_number(body: str | None, branch: str | None) -> int | None:
    m = BODY_ISSUE_RE.search(body or "")
    if m:
        return int(m.group(1))
    m = BRANCH_ISSUE_RE.search(branch or "")
    return int(m.group(1)) if m else None


def check(changed: list[str], issue: int | None) -> list[str]:
    if issue is None:
        return ["cannot tell the issue: put 'Closes #<issue>' in the PR body or name the "
                "branch '<issue>-<slug>'"]
    pattern = re.compile(rf"^{re.escape(WORKNOTE_DIR)}/{issue}-[^/]+\.md$")
    if any(pattern.match(p) for p in changed):
        return []
    return [f"PR does not touch a worknote for issue #{issue}: add or update "
            f"{WORKNOTE_DIR}/{issue}-<slug>.md in this PR"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", required=True)
    ap.add_argument("--head", default="HEAD")
    ap.add_argument("--branch", default=os.environ.get("GITHUB_HEAD_REF"))
    ap.add_argument("--body-file")
    args = ap.parse_args(argv)
    if not args.body_file and dependabot_pr():
        print(f"[{NAME}] Dependabot PR: no issue, worknote or footer to check; skipped (#52)")
        return 0
    issue = issue_number(pr_body(args.body_file), args.branch)
    return report(NAME, check(changed_files(args.base, args.head), issue))


if __name__ == "__main__":
    sys.exit(main())
