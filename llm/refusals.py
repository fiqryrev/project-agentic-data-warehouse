"""refusals: why Auto Ontology's text-to-SQL agent ends a golden answer without SQL (issue 34).

    uv run python -m llm.refusals --db data/build/dwh.duckdb

Auto Ontology does not report how an episode ended, but the gateway traces each model call with
its full prompt, so the agent's last call holds the whole episode: every tool call and every tool
result. For each golden answer in `fact__ops__answer` (answers from write mode dual on, M11), this
reads the episode from Langfuse, counts its tool calls and the validator's refusals, and names the
way it ended. Reads only; makes no model call.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dtm
import json
import sys
from pathlib import Path

import duckdb

from llm.observe import Langfuse, generation_key_alias, iso, read_env

PAD = dtm.timedelta(seconds=2)


def _json(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def episode_messages(gens: list[dict], question: str) -> list[dict] | None:
    """The longest prompt among the window's chat calls whose user turn is this question."""
    best = None
    for g in gens:
        msgs = _json(g.get("input"))
        if not isinstance(msgs, list) or len(msgs) < 2:
            continue
        user = str(msgs[1].get("content") or "")
        if question.strip() and question.strip() in user and (best is None or len(msgs) > len(best)):
            best = msgs
    return best


def classify(msgs: list[dict] | None) -> dict:
    """Counts and the way an episode ended, from its messages (system, user, then turns)."""
    if not msgs:
        return {"ending": "no_episode_found"}
    calls = [t for m in msgs if m.get("role") == "assistant" for t in (m.get("tool_calls") or [])]
    names = collections.Counter(t["function"]["name"] for t in calls)
    purposes = collections.Counter(str((_json(t["function"].get("arguments")) or {}).get("purpose", "sql"))
                                   for t in calls if t["function"]["name"] == "retrieve")
    results = [str(m.get("content") or "") for m in msgs if m.get("role") == "tool"]
    not_in_view = sum("Not in view" in r for r in results)
    repeated = sum("already made this exact call" in r for r in results)
    unknown = sum("Unknown column" in r or "Unknown table" in r for r in results)
    ran = sum(1 for r in results if r[:1].isdigit() and " rows" in r[:20])
    out_of_calls = any("No tool calls left" in str(m.get("content") or "") for m in msgs if m.get("role") == "user")
    if not_in_view and not ran:
        ending = "tables_never_in_view"
    elif out_of_calls:
        ending = "tool_budget_spent"
    else:
        ending = "other"
    return {"ending": ending, "tool_calls": len(calls), "retrieve_information": purposes.get("information", 0),
            "retrieve_sql": purposes.get("sql", 0), "run_sql": names.get("run_sql", 0), "queries_ran": ran,
            "not_in_view": not_in_view, "unknown_name": unknown, "repeated": repeated, "out_of_calls": out_of_calls}


def generations(lf: Langfuse, since: dtm.datetime, until: dtm.datetime) -> list[dict]:
    out, cursor = [], None
    while True:
        page = lf.call("GET", "/api/public/v2/observations?type=GENERATION&limit=50&fields=core,basic,io,metadata"
                       f"&fromStartTime={iso(since)}&toStartTime={iso(until)}"
                       + (f"&cursor={cursor}" if cursor else ""))
        out += page.get("data") or []
        cursor = (page.get("meta") or {}).get("cursor")
        if not cursor:
            return [g for g in out if generation_key_alias(g) == "auto-ontology"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", type=Path, default=Path("data/build/dwh.duckdb"))
    args = ap.parse_args(argv)
    con = duckdb.connect(str(args.db), read_only=True)
    try:
        answers = con.execute(
            "select trace_id, golden_id, golden_verdict_status, question_description, answer_started_at, "
            "answer_finished_at, coalesce(candidate_name, 'golden') from data_warehouse_layer.fact__ops__answer "
            "where is_golden and answer_finished_at is not null order by answer_started_at").fetchall()
    finally:
        con.close()
    lf = Langfuse(read_env())
    rows = []
    for tid, gid, verdict, question, started, finished, cand in answers:
        lo, hi = started.replace(tzinfo=dtm.UTC) - PAD, finished.replace(tzinfo=dtm.UTC) + PAD
        c = classify(episode_messages(generations(lf, lo, hi), question or ""))
        rows.append({"trace_id": tid, "golden_id": gid, "verdict": verdict, "candidate": cand, **c})
    by = collections.Counter((r["verdict"] == "refused", r["ending"]) for r in rows)
    print(f"[refusals] {len(rows)} golden answers read")
    for (refused, ending), n in sorted(by.items()):
        print(f"[refusals] {'refused' if refused else 'answered'}: {ending}: {n}")
    for r in rows:
        print(json.dumps(r, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
