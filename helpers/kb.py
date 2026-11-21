#!/usr/bin/env python3
"""kb: the distilled knowledge base (PLAN section 7), one lesson per file.

Entries live in `.agents/knowledge/entries/{de,da}/<id>-<slug>.md`: YAML frontmatter
(FIELDS) and a body with the sections of its kind (SECTIONS). `de-` is engineering (rule,
why, how to apply, example); `da-` is data (what values mean, with counts and their query).

    uv run python -m helpers.kb list [--kind de|da]
    uv run python -m helpers.kb search "late order rows" [-k 5]
    uv run python -m helpers.kb show da-0003
    uv run python -m helpers.kb new da "What a column's values mean"
    uv run python -m helpers.kb render          # regenerate the docs and the index

`render` writes GENERATED; never edit those by hand (`check_knowledge` compares them).
Search is keyword scoring over title, tags, paths and body: no network, no embeddings.
"""
from __future__ import annotations

import argparse
import datetime as dtm
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

try:
    from helpers.govlib import REPO
except ModuleNotFoundError:
    from govlib import REPO  # type: ignore

KB_DIR = Path(".agents/knowledge")
KINDS = {"de": "engineering", "da": "data"}
FIELDS = ("id", "title", "tags", "paths", "status", "created", "last_verified", "evidence",
          "supersedes")
STATUSES = ("active", "superseded", "retired")
SECTIONS = {"de": ("Rule", "Why", "How to apply", "Example"),
            "da": ("Meaning", "Counts", "Terms", "Data quality")}
GENERATED = {"de": Path("docs/engineering-distilled-knowledge.md"),
             "da": Path("docs/data-distilled-knowledge.md"),
             "index": KB_DIR / "index" / "entries.json"}
ID_RE = re.compile(r"^(de|da)-(\d{4})$")
WORD = re.compile(r"[a-z0-9_]+")
STOP = {"the", "a", "an", "of", "in", "on", "to", "is", "are", "and", "or", "for", "what",
        "why", "how", "does", "do", "we", "it", "by", "with", "from", "at", "as", "be"}


@dataclass
class Entry:
    path: Path                      # relative to the repo
    meta: dict
    body: str
    sections: dict[str, str] = field(default_factory=dict)

    @property
    def id(self) -> str:
        return str(self.meta.get("id", ""))

    @property
    def kind(self) -> str:
        return self.id[:2]

    @property
    def title(self) -> str:
        return str(self.meta.get("title", ""))


def parse(text: str, path: Path) -> Entry:
    """Split frontmatter and body; raise ValueError when the frontmatter is missing or bad."""
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not m:
        raise ValueError("no frontmatter between --- lines at the top")
    try:
        meta = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"frontmatter is not YAML ({exc})") from exc
    if not isinstance(meta, dict):
        raise ValueError("frontmatter is not a mapping")
    body = m.group(2)
    sections, current = {}, None
    for line in body.splitlines():
        if h := re.match(r"^## (.+?)\s*$", line):
            current = h.group(1)
            sections[current] = ""
        elif current is not None:
            sections[current] += line + "\n"
    return Entry(path=path, meta=meta, body=body, sections=sections)


def entry_files(root: Path = REPO) -> list[Path]:
    base = root / KB_DIR / "entries"
    return sorted(p for k in KINDS for p in (base / k).glob("*.md"))


def load(root: Path = REPO) -> tuple[list[Entry], list[str]]:
    """(entries, errors for files that cannot be parsed)."""
    entries, errors = [], []
    for p in entry_files(root):
        rel = p.relative_to(root)
        try:
            entries.append(parse(p.read_text(encoding="utf-8"), rel))
        except ValueError as exc:
            errors.append(f"{rel}: {exc}")
    return entries, errors


def _date(value) -> str:
    return value.isoformat() if isinstance(value, dtm.date) else str(value)


# ---- search -----------------------------------------------------------------------------

def terms(text: str) -> list[str]:
    return [w for w in WORD.findall(text.lower()) if w not in STOP]


def _stem(word: str) -> str:
    for suffix in ("ing", "es", "s", "ed"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    return word


def score(entry: Entry, query: str) -> float:
    fields = {
        3.0: entry.title,
        2.5: " ".join(map(str, entry.meta.get("tags") or [])),
        1.5: " ".join(map(str, entry.meta.get("paths") or [])).replace("/", " ").replace("__", " "),
        1.0: entry.body,
    }
    bags = {w: {_stem(t) for t in terms(text)} for w, text in fields.items()}
    total = 0.0
    for q in {_stem(t) for t in terms(query)}:
        total += max((w for w, bag in bags.items() if q in bag), default=0.0)
    return total if entry.meta.get("status") == "active" else total / 4


def search(entries: list[Entry], query: str, k: int = 5) -> list[tuple[float, Entry]]:
    ranked = sorted(((score(e, query), e) for e in entries), key=lambda x: (-x[0], x[1].id))
    return [(s, e) for s, e in ranked if s > 0][:k]


# ---- generated files --------------------------------------------------------------------

def render_doc(entries: list[Entry], kind: str) -> str:
    chosen = [e for e in sorted(entries, key=lambda e: e.id) if e.kind == kind]
    lines = [f"# {KINDS[kind].capitalize()} distilled knowledge",
             "",
             "Generated by `uv run python -m helpers.kb render` from "
             f"`.agents/knowledge/entries/{kind}/`; do not edit by hand.",
             ""]
    lines += ["| Id | Title | Status | Last verified |", "|---|---|---|---|"]
    lines += [f"| [{e.id}](#{e.id}) | {e.title} | {e.meta.get('status')} | "
              f"{_date(e.meta.get('last_verified'))} |" for e in chosen]
    for e in chosen:
        lines += ["", f"## {e.id}", "", f"**{e.title}**", "",
                  f"Tags: {', '.join(map(str, e.meta.get('tags') or []))}. "
                  f"Source: `{e.path.as_posix()}`.", ""]
        lines.append(e.body.strip().replace("\n## ", "\n### "))
    return "\n".join(lines).rstrip() + "\n"


def render_index(entries: list[Entry]) -> str:
    rows = [{"id": e.id, "kind": KINDS.get(e.kind, e.kind), "title": e.title,
             "tags": list(map(str, e.meta.get("tags") or [])),
             "paths": list(map(str, e.meta.get("paths") or [])),
             "status": e.meta.get("status"), "last_verified": _date(e.meta.get("last_verified")),
             "file": e.path.as_posix()} for e in sorted(entries, key=lambda e: e.id)]
    return json.dumps({"entries": rows}, indent=2, ensure_ascii=False) + "\n"


def rendered(entries: list[Entry]) -> dict[Path, str]:
    return {GENERATED["de"]: render_doc(entries, "de"),
            GENERATED["da"]: render_doc(entries, "da"),
            GENERATED["index"]: render_index(entries)}


# ---- new entry --------------------------------------------------------------------------

def next_id(entries: list[Entry], kind: str) -> str:
    nums = [int(m.group(2)) for e in entries if (m := ID_RE.match(e.id)) and m.group(1) == kind]
    return f"{kind}-{max(nums, default=0) + 1:04d}"


def template(entry_id: str, title: str, today: dtm.date) -> str:
    kind = entry_id[:2]
    head = yaml.safe_dump({"id": entry_id, "title": title, "tags": [], "paths": [],
                           "status": "active", "created": today, "last_verified": today,
                           "evidence": [], "supersedes": []}, sort_keys=False)
    body = "\n".join(f"## {s}\n\nTODO\n" for s in SECTIONS[kind])
    return f"---\n{head}---\n\n{body}"


def slug(title: str) -> str:
    return "-".join(terms(title))[:50].strip("-") or "entry"


# ---- CLI --------------------------------------------------------------------------------

def main(argv: list[str] | None = None, root: Path = REPO) -> int:
    ap = argparse.ArgumentParser(prog="kb", description="the distilled knowledge base")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("list")
    p.add_argument("--kind", choices=sorted(KINDS))
    p = sub.add_parser("search")
    p.add_argument("query")
    p.add_argument("-k", type=int, default=5)
    p = sub.add_parser("show")
    p.add_argument("id")
    p = sub.add_parser("new")
    p.add_argument("kind", choices=sorted(KINDS))
    p.add_argument("title")
    sub.add_parser("render")
    args = ap.parse_args(argv)

    entries, errors = load(root)
    for e in errors:
        print(f"WARNING {e}", file=sys.stderr)
    if args.cmd == "list":
        for e in sorted(entries, key=lambda e: e.id):
            if not args.kind or e.kind == args.kind:
                print(f"{e.id}  {e.meta.get('status'):<10}  {e.title}")
    elif args.cmd == "search":
        hits = search(entries, args.query, args.k)
        for s, e in hits:
            print(f"{s:5.1f}  {e.id}  {e.title}  ({e.path.as_posix()})")
        if not hits:
            print("no match")
            return 1
    elif args.cmd == "show":
        match = [e for e in entries if e.id == args.id]
        if not match:
            print(f"no entry {args.id}", file=sys.stderr)
            return 1
        print((root / match[0].path).read_text(encoding="utf-8"), end="")
    elif args.cmd == "new":
        entry_id = next_id(entries, args.kind)
        path = root / KB_DIR / "entries" / args.kind / f"{entry_id}-{slug(args.title)}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(template(entry_id, args.title, dtm.date.today()), encoding="utf-8")
        print(path.relative_to(root).as_posix())
    elif args.cmd == "render":
        for rel, text in rendered(entries).items():
            out = root / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(text, encoding="utf-8")
            print(f"wrote {rel.as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
