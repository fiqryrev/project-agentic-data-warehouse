"""label-prs: turn new human labels from the Langfuse queue into pull requests and issues (PLAN 8.4).

    make label-prs              # dry run: list new labels and what each would become
    make label-prs OPEN=1       # create the issue, branch, files, PR (and dbt issues)

What a label becomes (the label form, infra/langfuse/scores.yaml):

    correct, not a golden answer      a golden question (evals/golden/), reference SQL = the
                                      labeller's correct_sql, else the answer's own SQL
    wrong_definition, wrong_filter    a da- knowledge entry: the labeller's note and correct
                                      answer, the correct SQL run on the snapshot; the ontology
                                      correction is proposed in the PR body, never applied
    wrong_grain, wrong_number         a dbt issue (a model, test or rpt table is missing)
    anything else                     recorded only

Every handled label is recorded in evals/labels/processed.yaml (trace, labeller, verdict,
outcome), so a label never produces two pull requests. The pull request comes from its own
issue, worktree and worknote, and passes the same checks as code; its AI usage footer is
rendered by helpers/ai_usage_footer.py, so this runs inside an agent session (skill
label-review). Nothing is merged. Reads the snapshot read-only; makes no model call.
"""
from __future__ import annotations

import argparse
import datetime as dtm
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

from helpers import kb
from helpers.ai_usage_footer import project_dir_for
from llm import golden as gd
from llm.ask import SNAPSHOT
from llm.observe import Langfuse, iso, parse_time, read_env

REPO = Path(__file__).resolve().parents[1]
PROCESSED = Path("evals/labels/processed.yaml")
FIELDS = ("verdict", "reasoning_ok", "correct_answer", "correct_sql", "note")
class _Block(yaml.SafeDumper):
    """Multi-line strings (SQL) as `|` blocks, as the hand-written golden files have them."""


_Block.add_representer(str, lambda d, v: d.represent_scalar("tag:yaml.org,2002:str", v, style="|" if "\n" in v else None))

TO_GOLDEN, TO_KNOWLEDGE, TO_ISSUE = ("correct",), ("wrong_definition", "wrong_filter"), ("wrong_grain", "wrong_number")


# --- reading labels --------------------------------------------------------------------------

def labels_from_scores(scores: list[dict]) -> list[dict]:
    """One label per (trace, labeller) from the label form's scores; a label needs a verdict."""
    out: dict[tuple, dict] = {}
    for s in sorted(scores, key=lambda s: str(s.get("timestamp"))):
        if s.get("name") not in FIELDS:
            continue
        key = (s.get("traceId"), s.get("authorUserId") or "api")
        lab = out.setdefault(key, {"trace_id": key[0], "labeler": key[1], "source": s.get("source"),
                                   "labeled_at": s.get("timestamp")})
        lab[s["name"]] = s.get("stringValue") if s.get("stringValue") is not None else s.get("value")
        lab["labeled_at"] = max(str(lab["labeled_at"]), str(s.get("timestamp")))
    return [lab for lab in out.values() if lab.get("verdict")]


def read_processed(path: Path) -> list[dict]:
    return (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("labels", []) if path.exists() else []


def new_labels(labels: list[dict], processed: list[dict]) -> list[dict]:
    done = {(p["trace_id"], p["labeler"]) for p in processed}
    return [lab for lab in labels if (lab["trace_id"], lab["labeler"]) not in done]


def outcome_of(label: dict, answer: dict) -> str:
    v = label["verdict"]
    if v in TO_GOLDEN:
        return "already_golden" if answer.get("golden_id") else "golden"
    if v in TO_KNOWLEDGE:
        return "knowledge"
    if v in TO_ISSUE:
        return "issue"
    return "recorded"


def answer_of(lf: Langfuse, trace_id: str, labeled_at: str) -> dict:
    """The answer trace's root span `ask`, read from observations v2 (it holds traces from before
    the switch to write mode dual too)."""
    until = parse_time(labeled_at)
    path = (f"/api/public/v2/observations?traceId={trace_id}&name=ask&fields=core,basic,io,metadata&limit=5"
            f"&fromStartTime={iso(until - dtm.timedelta(days=90))}&toStartTime={iso(until)}")
    obs = (lf.call("GET", path).get("data") or [{}])[0]
    out, inp, meta = (_obj(obs.get(k)) for k in ("output", "input", "metadata"))
    meta = {k.removeprefix("attributes.langfuse.trace.metadata."): v for k, v in meta.items()}
    return {"question": inp.get("question"), "answer": out.get("answer"), "sql": out.get("sql"),
            "golden_id": _obj(meta).get("golden_id"), "started_at": obs.get("startTime")}


def _obj(value) -> dict:
    import json
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return {}
    return value if isinstance(value, dict) else {}


# --- untrusted text --------------------------------------------------------------------------
# A labeller's note and answer, the question, and the chat's answer and SQL are free text from
# Langfuse. They land in knowledge entries that coding agents read, and in issues and PR bodies on
# a public repository (S4, security review 2026-11-23). Every such value passes sanitize().

CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f\u200b-\u200f\u202a-\u202e\u2060-\u2064\ufeff]")


def sanitize(value, limit: int = 500) -> str:
    """One line of inert text: whitespace collapsed, capped at `limit`; `@name` mentions, links
    (with a scheme, protocol-relative, `www.`, Markdown `[text](target)`), backticks (code spans
    and fences) and HTML tags neutralised, so it notifies nobody, links nowhere and cannot close
    the fenced block it is quoted in."""
    text = CONTROL_RE.sub("", "" if value is None else str(value))
    text = " ".join(text.split())
    text = text.replace("`", "'").replace("<", "\u2039").replace(">", "\u203a")
    text = re.sub(r"@(?=\w)", "(at)", text)                      # mentions and e-mail addresses
    text = text.replace("://", "[:]//")                          # every scheme: https, ftp, ...
    text = re.sub(r"(^|[\s(\[])//(?=[\w.-])", r"\1/ /", text)       # protocol-relative //host
    text = text.replace("](", "] (")                             # Markdown links and images
    text = re.sub(r"(?i)\bwww\.", "www[.]", text)                # bare links GitHub would autolink
    return text if len(text) <= limit else text[:limit - 1] + "\u2026"


def quoted(lines: list[str]) -> str:
    """Untrusted text as an agent must read it: the fixed data line, then a ```text block."""
    return kb.QUOTED_LINE + "\n\n```text\n" + "\n".join(lines) + "\n```"


# --- what a label writes ---------------------------------------------------------------------

def slug(text: str, words: int = 6) -> str:
    return "-".join(re.findall(r"[a-z0-9]+", (text or "label").lower())[:words]) or "label"


def next_id(folder: Path, prefix: str) -> int:
    nums = [int(m.group(1)) for p in folder.glob(f"{prefix}-*") if (m := re.match(rf"{prefix}-(\d+)", p.name))]
    return max(nums, default=0) + 1


def snapshot_facts(sql: str | None) -> tuple[str | None, list]:
    """(snapshot day, rows of sql) on the published snapshot, read-only."""
    if not SNAPSHOT.exists():
        return None, []
    con = gd.connect(SNAPSHOT)
    try:
        day = gd.snapshot_day(con)
        rows = gd.run_sql(con, sql)[1] if sql else []
    except Exception as e:                    # noqa: BLE001 (the entry says the SQL failed)
        rows = [f"the SQL fails on the snapshot: {str(e).splitlines()[0][:120]}"]
    finally:
        con.close()
    return day, rows


def golden_doc(qid: str, label: dict, answer: dict, day: str | None) -> dict:
    """needs_day is the newest date the SQL names, else the snapshot's last day."""
    sql = (label.get("correct_sql") or answer["sql"] or "").strip()
    dates = sorted(re.findall(r"\d{4}-\d{2}-\d{2}", sql))
    return {"id": qid, "question": answer["question"], "reference_sql": sql + "\n",
            "kind": "scalar", "tolerance_pct": 0.5, "needs_day": dates[-1] if dates else day}


def knowledge_entry(did: str, label: dict, answer: dict, day: str | None, rows: list, today: str) -> str:
    """A `da-` entry: our own words outside the fences, everything from the label or the chat
    inside ```text (and the SQL in ```sql) blocks, sanitised (check_knowledge, label entries)."""
    sql = sanitize(label.get("correct_sql") or answer.get("sql") or "", 2000)
    whose = "the labeller's correct SQL" if label.get("correct_sql") else "the chat's own SQL (labelled wrong)"
    question = sanitize(answer.get("question"), 300)
    verdict = slug(label.get("verdict"), 3).replace("-", "_")
    tags = sorted({kb.LABEL_TAG, verdict.replace("_", "-")} | set(re.findall(r"[a-z]{4,}", question.lower())[:6]))
    # The title is outside every fence, so it carries no label or chat text at all: a pattern can
    # only miss an instruction, never vouch for text (Codex review on #46). The reviewer tightens
    # it to the misread term (skill label-review); search finds the question in the body.
    title = f"Label {verdict}: {did}"
    trace = slug(label.get("trace_id"), 1)
    return f"""---
id: {did}
title: "{title}"
tags: [{', '.join(tags)}]
paths: [{PROCESSED.as_posix()}]
status: active
created: {today}
last_verified: {today}
evidence:
  - "{PROCESSED.as_posix()}::{trace}"
supersedes: []
---

## Meaning

A person labelled one of Auto Ontology's answers as `{verdict}` (reasoning_ok:
{slug(label.get('reasoning_ok') or 'not rated', 3).replace('-', ' ')}). What they wrote:

{quoted([f"Question: {question}", f"Note: {sanitize(label.get('note')) or '(no note)'}",
         f"Correct answer, as labelled: {sanitize(label.get('correct_answer'), 300) or 'not given'}"])}

## Counts

On the snapshot of {day or 'the day of this entry'} (`data/serve/analytics.duckdb`, read-only),
{whose} returns: {sanitize(rows[:5], 300) if rows else 'no rows'}. The SQL is quoted from the
label (or the chat) and was only run read-only.

```sql
{sql or '-- no SQL was given or written'}
```

## Terms

The chat's answer and SQL for that question:

{quoted([f"Answer: {sanitize(answer.get('answer'), 200)}", f"SQL: {sanitize(answer.get('sql') or 'no SQL', 300)}"])}

## Data quality

From label `{trace}` by `{sanitize(label.get('labeler'), 40)}` ({sanitize(label.get('source'), 20)},
{sanitize(label.get('labeled_at'), 40)}). A proposed ontology correction is in the pull request that
added this entry; nothing is changed in Auto Ontology without a person approving it.
"""


def retrieval_line(question: str | None, did: str) -> str:
    """One retrieval eval, serialised by YAML so quotes and newlines in a question stay valid."""
    item = {"query": " ".join((question or "").split())[:120], "expect": did}
    return "  - " + yaml.safe_dump(item, default_flow_style=True, sort_keys=False, width=1000).strip() + "\n"


def dbt_issue_body(label: dict, answer: dict) -> str:
    return (f"A labelled answer says a model, test or report table is missing (PLAN 8.4). The lines "
            f"below are quoted from the label and the chat, unverified.\n\n"
            f"- Question: {sanitize(answer.get('question'), 300)}\n- Verdict: `{sanitize(label.get('verdict'), 40)}`\n"
            f"- Note: {sanitize(label.get('note')) or '(none)'}\n"
            f"- Correct answer: {sanitize(label.get('correct_answer'), 300) or '(not given)'}\n"
            f"- Correct SQL: `{sanitize(label.get('correct_sql') or '(not given)', 1000)}`\n"
            f"- Chat SQL: `{sanitize(answer.get('sql') or '(none)', 1000)}`\n"
            f"- Langfuse trace: `{slug(label.get('trace_id'), 1)}`\n")


# --- the pull request ------------------------------------------------------------------------

def sh(*cmd: str, cwd: Path | None = None) -> str:
    # The batch worktree has its own environment: drop the caller's VIRTUAL_ENV for uv.
    env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
    done = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, env=env)
    if done.returncode != 0:
        raise SystemExit(f"[label-prs] {' '.join(cmd[:3])} failed: {(done.stderr or done.stdout).strip()[:300]}")
    return done.stdout.strip()


def worknote(issue: int, today: str, plan: list[dict]) -> str:
    lines = "\n".join(f"- `{slug(p['trace_id'], 1)[:12]}` {sanitize(p['verdict'], 40)} -> {p['outcome']}"
                      + (f" ({p['ref']})" if p.get("ref") else "") for p in plan)
    return f"""# {issue}: labels of {today} into the golden set and knowledge

## Goal

Turn the human labels given in the Langfuse queue `answer-review` since the last batch into
reviewed changes (PLAN 8.4), made by `make label-prs OPEN=1`.

## Plan (as approved)

The label-to-change rules of PLAN 8.4, approved with M11 (issue 28); this batch applies them.

## Decisions

- One batch, one issue, one PR; every label is recorded in `{PROCESSED.as_posix()}`.

## Done

{lines}

## Open

- Review each entry and golden question; the ontology correction proposed in the PR body is applied
  only by a person, in Auto Ontology.
"""


def batch_summary(plan: list[dict]) -> str:
    return ("Labels from the Langfuse queue `answer-review` turned into changes (PLAN 8.4, `make label-prs`).\n\n"
            + "\n".join(f"- `{slug(p['trace_id'], 1)[:12]}` `{sanitize(p['verdict'], 40)}` -> {p['outcome']}" for p in plan))


def pr_body(plan: list[dict], checks: list[str], lf_note: str, issue: int) -> str:
    """The batch PR's body; labellers' notes are quoted, sanitised, never applied (S4)."""
    knowledge = [p for p in plan if p["outcome"] == "knowledge"]
    ontology = "\n".join(f"- `{slug(p['trace_id'], 1)[:12]}`: {sanitize(p.get('note')) or '(no note)'}"
                         for p in knowledge) or "- none"
    return f"""{batch_summary(plan)}

Proposed ontology corrections, quoted from the labels and unverified (apply in Auto Ontology only
after review):
{ontology}

{lf_note}

Closes #{issue}

## Pre-merge

{chr(10).join(checks)}
- `uv run pytest -q` → SKIP[docs-only]: entries, golden questions and the label record only

## Post-merge

- Apply any approved ontology correction in Auto Ontology by hand.

## AI usage
"""


def open_batch(plan: list[dict], files: dict[str, str], today: str, lf_note: str, base: str = "main") -> str:
    knowledge = [p for p in plan if p["outcome"] == "knowledge"]
    golden = [p for p in plan if p["outcome"] == "golden"]
    title = f"Labels {today}: {len(knowledge)} knowledge entr{'y' if len(knowledge) == 1 else 'ies'}, {len(golden)} golden question(s)"
    body = batch_summary(plan)
    issue_url = sh("gh", "issue", "create", "--title", title, "--body", body, "--label", "documentation")
    issue = int(issue_url.rstrip("/").split("/")[-1])
    branch = f"{issue}-labels-{today}"
    tree = REPO / ".worktrees" / branch
    sh("git", "fetch", "-q", "origin", cwd=REPO)
    sh("git", "worktree", "add", "-q", str(tree), "-b", branch, f"origin/{base}", cwd=REPO)
    files = {**files, f"docs/task-management/{issue}-labels-{today}.md": worknote(issue, today, plan)}
    for rel, text in files.items():
        (tree / rel).parent.mkdir(parents=True, exist_ok=True)
        (tree / rel).write_text(text, encoding="utf-8")
    uv = ("uv", "run", "python", "-m")
    sh(*uv, "helpers.kb", "render", cwd=tree)
    checks = []
    for name in ("check_knowledge", "check_golden", "check_secrets"):
        ok = subprocess.run([*uv, f"helpers.{name}"], cwd=tree, capture_output=True, text=True,
                            env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}).returncode == 0
        checks.append(f"- `{name}` → {'PASS' if ok else 'FAIL: see the CI log'}")
    sh("git", "add", "-A", cwd=tree)
    sh("git", "commit", "-q", "-m", f"docs: {title.lower()}\n\nCloses #{issue}", cwd=tree)
    sh("git", "push", "-q", "-u", "origin", branch, cwd=tree)
    body_file = tree / ".pr-body.md"
    body_file.write_text(pr_body(plan, checks, lf_note, issue), encoding="utf-8")
    # The session transcript belongs to the checkout the agent runs in, not to the batch worktree.
    sh("uv", "run", "python", "helpers/ai_usage_footer.py", "render", "--body-file", str(body_file),
       "--prior-from-gh", "--project-dir", str(project_dir_for(REPO)), cwd=tree)
    sh(*uv, "helpers.check_pr_body", "--body-file", str(body_file), cwd=tree)
    url = sh("gh", "pr", "create", "--base", base, "--head", branch, "--title", f"docs: {title}",
             "--body-file", str(body_file), "--label", "documentation", cwd=tree)
    body_file.unlink()
    return url


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--open", action="store_true", help="create the issue, branch, files and pull request")
    ap.add_argument("--base", default="main", help="branch the pull request starts from and targets")
    args = ap.parse_args(argv)
    lf = Langfuse(read_env())
    labels = labels_from_scores(lf.pages("/api/public/scores?dataType=CATEGORICAL&name=verdict")
                                + [s for n in FIELDS[1:] for s in lf.pages(f"/api/public/scores?name={n}")])
    processed = read_processed(REPO / PROCESSED)
    todo = new_labels(labels, processed)
    if not todo:
        print("[label-prs] no new label")
        return 0
    today = dtm.datetime.now(dtm.UTC).date().isoformat()
    plan, files, issues = [], {}, []
    gnext = next_id(REPO / gd.GOLDEN_DIR, "g")
    dnext = next_id(REPO / ".agents/knowledge/entries/da", "da")
    evals = (REPO / ".agents/knowledge/evals/retrieval.yaml").read_text(encoding="utf-8")
    for lab in todo:
        ans = answer_of(lf, lab["trace_id"], lab["labeled_at"])
        out = outcome_of(lab, ans)
        item = {"trace_id": lab["trace_id"], "labeler": lab["labeler"], "verdict": lab["verdict"],
                "outcome": out, "labeled_at": lab["labeled_at"], "note": lab.get("note")}
        if out == "golden":
            day, _ = snapshot_facts(None)
            qid = f"g-{gnext:04d}"
            gnext += 1
            files[f"evals/golden/{qid}-{slug(ans['question'])}.yaml"] = yaml.dump(
                golden_doc(qid, lab, ans, day), Dumper=_Block, sort_keys=False, width=100)
            item["ref"] = qid
        elif out == "knowledge":
            day, rows = snapshot_facts(lab.get("correct_sql") or ans.get("sql"))
            did = f"da-{dnext:04d}"
            dnext += 1
            files[f".agents/knowledge/entries/da/{did}-{slug(ans['question'])}.md"] = knowledge_entry(
                did, lab, ans, day, rows, today)
            evals += retrieval_line(ans["question"], did)
            item["ref"] = did
        elif out == "issue" and args.open:
            item["ref"] = sh("gh", "issue", "create", "--title",
                             f"dbt: labelled {sanitize(lab['verdict'], 40)}: {sanitize(ans['question'], 60)}",
                             "--body", dbt_issue_body(lab, ans), "--label", "bug")
            issues.append(item["ref"])
        plan.append(item)
        print(f"[label-prs] {lab['trace_id'][:12]} {lab['verdict']} ({lab['labeler']}) -> {out}"
              + (f" {item.get('ref')}" if item.get("ref") else ""))
    if not args.open:
        print(f"[label-prs] dry run: {len(plan)} label(s); OPEN=1 to create the pull request")
        return 0
    record = {"labels": processed + [{k: v for k, v in p.items() if k != "note"} for p in plan]}
    files[PROCESSED.as_posix()] = ("# Labels handled by make label-prs (llm/labels.py); one row per trace and labeller.\n"
                                   + yaml.safe_dump(record, sort_keys=False, width=100))
    files[".agents/knowledge/evals/retrieval.yaml"] = evals
    if not any(p["outcome"] in ("golden", "knowledge") for p in plan):
        print(f"[label-prs] nothing to change in files; issues: {issues or 'none'}. The record update needs a PR:")
    lf_note = f"dbt issues opened: {', '.join(issues)}" if issues else "No dbt issue in this batch."
    print(f"[label-prs] pull request: {open_batch(plan, files, today, lf_note, args.base)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
