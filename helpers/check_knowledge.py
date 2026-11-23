#!/usr/bin/env python3
"""check_knowledge: the knowledge base stays true, current and findable (PLAN section 7).

For every entry under .agents/knowledge/entries/{de,da}/:
- frontmatter has every field in kb.FIELDS; `id` is `<kind>-NNNN`, unique, matches its folder
  and starts its file name; `status` is active, superseded or retired; dates are dates, with
  created <= last_verified <= today; `tags` is a non-empty list;
- expiry: an active entry is verified again within MAX_AGE days (`da-` 90, matching the
  verify-literal rule; `de-` 365); within WARN_DAYS of that it warns;
- `paths` exist; every `evidence` item resolves: `<path>` exists, `<path>::<text>` also
  contains the text; `supersedes` names existing entries that are not active;
- the body has the sections of its kind; a `da-` entry's Counts section carries the SQL
  behind its numbers (a ```sql block), so every number cites its query;
- a `da-` entry tagged `label` (built from a human label) quotes the label and chat text in a
  ```text block under kb.QUOTED_LINE, and has no instruction-like text outside its fenced
  blocks or in its title (kb.INSTRUCTION_RE);
- the generated docs and index equal `kb render` output;
- retrieval: each question in .agents/knowledge/evals/retrieval.yaml finds its expected
  entry in the top `k` results of `kb search`, for at least `floor` of the questions.
"""
from __future__ import annotations

import argparse
import datetime as dtm
import re
import sys
from pathlib import Path

import yaml

try:
    from helpers import kb
    from helpers.govlib import REPO, report
except ModuleNotFoundError:
    import kb  # type: ignore
    from govlib import REPO, report  # type: ignore

NAME = "check_knowledge"
MAX_AGE = {"da": 90, "de": 365}
WARN_DAYS = 14
CLOCK_SLACK = dtm.timedelta(days=1)   # an entry dated in UTC+14 is still "today" in CI's UTC
EVALS = kb.KB_DIR / "evals" / "retrieval.yaml"


def _as_date(value) -> dtm.date | None:
    if isinstance(value, dtm.date):
        return value
    try:
        return dtm.date.fromisoformat(str(value))
    except ValueError:
        return None


def resolve(item: str, root: Path) -> str | None:
    """None when the evidence resolves, else the reason it does not."""
    if not isinstance(item, str):
        return f"evidence {item!r} is not a string; quote an item that contains ': '"
    path, _, text = item.partition("::")
    target = root / path.strip()
    if not path.strip() or not target.exists():
        return f"evidence '{item}': {path.strip() or '(empty)'} does not exist"
    if text:
        if not target.is_file():
            return f"evidence '{item}': {path.strip()} is not a file"
        if text.strip() not in target.read_text(encoding="utf-8", errors="replace"):
            return f"evidence '{item}': {path.strip()} does not contain '{text.strip()}'"
    return None


def entry_errors(e: kb.Entry, root: Path, today: dtm.date,
                 ids: dict[str, kb.Entry]) -> tuple[list[str], list[str]]:
    where = e.path.as_posix()
    errors, warnings = [], []
    missing = [f for f in kb.FIELDS if f not in e.meta]
    if missing:
        return [f"{where}: frontmatter is missing {', '.join(missing)}"], []
    m = kb.ID_RE.match(e.id)
    if not m:
        return [f"{where}: id '{e.id}' is not de-NNNN or da-NNNN"], []
    if e.path.parent.name != e.kind:
        errors.append(f"{where}: a {e.kind}- entry belongs in entries/{e.kind}/")
    if not e.path.name.startswith(e.id + "-"):
        errors.append(f"{where}: the file name starts with its id ('{e.id}-<slug>.md')")
    if not e.title.strip():
        errors.append(f"{where}: empty title")
    tags = e.meta.get("tags")
    if not isinstance(tags, list) or not tags:
        errors.append(f"{where}: tags is a non-empty list")
    status = e.meta.get("status")
    if status not in kb.STATUSES:
        errors.append(f"{where}: status '{status}' is not one of {', '.join(kb.STATUSES)}")
    created, verified = _as_date(e.meta["created"]), _as_date(e.meta["last_verified"])
    if created is None or verified is None:
        errors.append(f"{where}: created and last_verified are dates (YYYY-MM-DD)")
    else:
        if created > verified:
            errors.append(f"{where}: created is after last_verified")
        if verified > today + CLOCK_SLACK:
            errors.append(f"{where}: last_verified {verified} is in the future")
        age = (today - verified).days
        limit = MAX_AGE[e.kind]
        if status == "active" and age > limit:
            errors.append(f"{where}: stale, last verified {verified} ({age} days; a {e.kind}- "
                          f"entry is verified again within {limit}); re-check it and bump "
                          f"last_verified, or retire it")
        elif status == "active" and age > limit - WARN_DAYS:
            warnings.append(f"{where}: expires in {limit - age} days; re-verify it soon")
    for p in e.meta.get("paths") or []:
        if not (root / str(p)).exists():
            errors.append(f"{where}: path '{p}' does not exist")
    evidence = e.meta.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        errors.append(f"{where}: no evidence; name the file (and text) that shows it")
    else:
        errors += [f"{where}: {r}" for item in evidence if (r := resolve(item, root))]
    for old in e.meta.get("supersedes") or []:
        if old not in ids:
            errors.append(f"{where}: supersedes '{old}', which does not exist")
        elif ids[old].meta.get("status") == "active":
            errors.append(f"{where}: supersedes '{old}', which is still active")
    for section in kb.SECTIONS[e.kind]:
        if not e.sections.get(section, "").strip():
            errors.append(f"{where}: section '## {section}' is missing or empty")
    if e.kind == "da" and "```sql" not in e.sections.get("Counts", ""):
        errors.append(f"{where}: the Counts section has no ```sql block; every number cites its query")
    if e.kind == "da" and kb.LABEL_TAG in (tags if isinstance(tags, list) else []):
        errors += [f"{where}: {r}" for r in label_entry_errors(e)]
    return errors, warnings


def label_entry_errors(e: kb.Entry) -> list[str]:
    """A `da-` entry built from a label keeps its quoted text fenced and marked as data."""
    out = []
    if not re.search(re.escape(kb.QUOTED_LINE) + r"\s*\n\s*\n?```text\n", e.body):
        out.append("a label entry quotes its label and chat text in a ```text block right after "
                   f"the line '{kb.QUOTED_LINE[:40]}...' (kb.QUOTED_LINE)")
    for where, text in (("title", e.title), ("body outside its fenced blocks", kb.outside_fences(e.body))):
        if (m := kb.INSTRUCTION_RE.search(text)):
            out.append(f"instruction-like text in the {where} ('{m.group(0)}'); quoted input belongs "
                       "in the fenced block under kb.QUOTED_LINE")
    return out


def retrieval(entries: list[kb.Entry], evals: dict) -> tuple[list[str], float]:
    cases = evals.get("cases") or []
    k, floor = int(evals.get("k", 3)), float(evals.get("floor", 0.9))
    if not cases:
        return ["retrieval eval has no cases"], 0.0
    misses = []
    for case in cases:
        top = [e.id for _, e in kb.search(entries, case["query"], k)]
        if case["expect"] not in top:
            misses.append(f"'{case['query']}' -> {top} (expected {case['expect']})")
    recall = 1 - len(misses) / len(cases)
    if recall < floor:
        return [f"retrieval recall@{k} is {recall:.2f}, below the floor {floor:.2f}; misses: "
                + "; ".join(misses)], recall
    return [], recall


def check(root: Path = REPO, today: dtm.date | None = None) -> tuple[list[str], list[str]]:
    today = today or dtm.date.today()
    entries, errors = kb.load(root)
    warnings: list[str] = []
    ids: dict[str, kb.Entry] = {}
    for e in entries:
        if e.id in ids:
            errors.append(f"{e.path.as_posix()}: id {e.id} is also used by {ids[e.id].path.as_posix()}")
        ids[e.id] = e
    for e in entries:
        errs, warns = entry_errors(e, root, today, ids)
        errors += errs
        warnings += warns
    for rel, text in kb.rendered(entries).items():
        target = root / rel
        if not target.is_file() or target.read_text(encoding="utf-8") != text:
            errors.append(f"{rel.as_posix()} is out of date; run `uv run python -m helpers.kb render`")
    evals_path = root / EVALS
    if not evals_path.is_file():
        errors.append(f"{EVALS.as_posix()} is missing")
    else:
        errs, recall = retrieval(entries, yaml.safe_load(evals_path.read_text(encoding="utf-8")) or {})
        errors += errs
        if not errs:
            print(f"[{NAME}] {len(entries)} entries; retrieval recall {recall:.2f}")
    return errors, warnings


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--today", help="check as of this date (YYYY-MM-DD)")
    args = ap.parse_args(argv)
    today = dtm.date.fromisoformat(args.today) if args.today else None
    errors, warnings = check(REPO, today)
    return report(NAME, errors, warnings)


if __name__ == "__main__":
    sys.exit(main())
