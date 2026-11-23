#!/usr/bin/env python3
"""check_pr_body: the PR body has the agreed sections, tokens and footer.

- `## Pre-merge` section: every list item ends in `→ PASS`, `→ FAIL: <reason>` or
  `→ SKIP[<rule>]: <reason>`. A FAIL item blocks the merge too.
- `## Post-merge` section is present (its items run after merge, so they carry no token).
- The body ends with the `## AI usage` footer in the fixed six-line shape (PLAN section 8.7),
  rendered by helpers/ai_usage_footer.py.
- No tool watermark ("Generated with ...", "Co-Authored-By:").

Usage: check_pr_body.py [--body-file FILE]   (in CI the body comes from the PR event)
"""
from __future__ import annotations

import argparse
import re
import sys

try:
    from helpers.ai_usage_footer import FOOTER_LABELS, HEADING_RE, WATERMARK_RE
    from helpers.govlib import dependabot_pr, pr_body, report
except ModuleNotFoundError:  # run as a script from helpers/
    from ai_usage_footer import FOOTER_LABELS, HEADING_RE, WATERMARK_RE  # type: ignore
    from govlib import dependabot_pr, pr_body, report  # type: ignore

NAME = "check_pr_body"
NUM = r"\d{1,3}(?:,\d{3})*"
USD = rf"\${NUM}\.\d{{2}}"
USAGE = rf"({NUM}) \(({USD})\) - Cache hit \(({NUM}), ({USD})\)"
MODEL = r"[A-Za-z0-9._:/@-]+ \(effort [a-z0-9/_-]+\)"
LINE_RES = {
    "Harness Tool": re.compile(r"^Harness Tool: \S.*$"),
    "Model Name": re.compile(rf"^Model Name: {MODEL}(?:, {MODEL})*$"),
    "Input Token Usage": re.compile(rf"^Input Token Usage: {USAGE}$"),
    "Output Token Usage": re.compile(rf"^Output Token Usage: {USAGE}$"),
    "Total Token": re.compile(rf"^Total Token: {USAGE}$"),
    "Metadata": re.compile(r"^Metadata: \S.*$"),
}
TOKEN_RE = re.compile(r"→ (?:PASS|FAIL: \S.*|SKIP\[[^\]\s]+\]: \S.*)\s*$")
ITEM_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
LEDGER_LINE_RE = re.compile(r"^<!-- ai-usage-ledger: \{.*\} -->$")


def _num(s: str) -> int:
    return int(s.replace(",", ""))


def _usd(s: str) -> float:
    return float(s.replace("$", "").replace(",", ""))


def sections(body: str) -> dict[str, str]:
    """Map lower-cased `## ` heading text to its content (outside code fences)."""
    out: dict[str, str] = {}
    current, buf, fence = None, [], False
    for line in body.splitlines():
        if line.strip().startswith("```"):
            fence = not fence
        if not fence and line.startswith("## "):
            if current is not None:
                out[current] = "\n".join(buf)
            current, buf = line[3:].strip().lower(), []
            continue
        if current is not None:
            buf.append(line)
    if current is not None:
        out[current] = "\n".join(buf)
    return out


def _find(secs: dict[str, str], prefix: str) -> str | None:
    for name, text in secs.items():
        if name.startswith(prefix):
            return text
    return None


def check_pre_merge(body: str) -> list[str]:
    secs = sections(body)
    errors = []
    pre = _find(secs, "pre-merge")
    if pre is None:
        errors.append("missing '## Pre-merge' section (the test plan with result tokens)")
    else:
        items, fence = [], False
        for line in pre.splitlines():
            if line.strip().startswith("```"):
                fence = not fence
                continue
            if not fence and ITEM_RE.match(line):
                items.append(line.strip())
        if not items:
            errors.append("'## Pre-merge' has no items")
        for item in items:
            if not TOKEN_RE.search(item):
                errors.append(
                    f"pre-merge item has no result token (→ PASS | → FAIL: reason | "
                    f"→ SKIP[rule]: reason): {item}"
                )
            elif "→ FAIL:" in item:
                errors.append(f"pre-merge item reports FAIL: {item}")
    if _find(secs, "post-merge") is None:
        errors.append("missing '## Post-merge' section")
    return errors


def check_footer(body: str) -> list[str]:
    found = list(HEADING_RE.finditer(body))
    if not found:
        return ["missing the '## AI usage' footer; render it with helpers/ai_usage_footer.py"]
    tail = body[found[-1].end():].strip("\n").splitlines()
    tail = [ln.rstrip() for ln in tail]
    while tail and not tail[-1]:
        tail.pop()
    errors = []
    if len(tail) < 8 or tail[0] != "```text" or tail[7] != "```":
        return ["the '## AI usage' footer must be a ```text block of exactly six lines"]
    extra = tail[8:]
    if len(extra) > 1 or (extra and not LEDGER_LINE_RE.match(extra[0])):
        errors.append("only the hidden ledger comment may follow the footer block; the footer "
                      "must end the body")
    lines = tail[1:7]
    parsed = {}
    for label, line in zip(FOOTER_LABELS, lines, strict=True):     # six of each, checked above
        m = LINE_RES[label].match(line)
        if not m:
            errors.append(f"footer line '{label}' has the wrong shape: {line}")
        else:
            parsed[label] = m.groups()
    if errors:
        return errors
    i_tok, i_usd, i_hit, i_hit_usd = parsed["Input Token Usage"]
    o_tok, o_usd, o_hit, o_hit_usd = parsed["Output Token Usage"]
    t_tok, t_usd, t_hit, t_hit_usd = parsed["Total Token"]
    if _num(o_hit) != 0 or _usd(o_hit_usd) != 0:
        errors.append("output tokens are never cached; its cache hit must be (0, $0.00)")
    if _num(t_tok) != _num(i_tok) + _num(o_tok):
        errors.append("Total Token tokens must equal input plus output")
    if abs(_usd(t_usd) - _usd(i_usd) - _usd(o_usd)) > 0.011:
        errors.append("Total Token cost must equal input plus output cost")
    if (t_hit, t_hit_usd) != (i_hit, i_hit_usd):
        errors.append("Total Token cache hit must equal the input cache hit")
    if "list-price estimate, not money paid" not in lines[5]:
        errors.append("Metadata must say 'list-price estimate, not money paid'")
    return errors


def check_watermark(body: str) -> list[str]:
    return [f"tool watermark in PR body: {ln.strip()}" for ln in body.splitlines()
            if WATERMARK_RE.search(ln)]


def check(body: str) -> list[str]:
    return check_pre_merge(body) + check_footer(body) + check_watermark(body)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--body-file")
    args = ap.parse_args(argv)
    if not args.body_file and dependabot_pr():
        print(f"[{NAME}] Dependabot PR: no issue, worknote or footer to check; skipped (#52)")
        return 0
    body = pr_body(args.body_file)
    if body is None:
        print(f"[{NAME}] no PR body (not a pull_request event and no --body-file); skipped")
        return 0
    return report(NAME, check(body))


if __name__ == "__main__":
    sys.exit(main())
