"""golden: ask every golden question, score the answers, send the doubtful ones to a person (PLAN 8.3).

    make golden DS=2026-01-08                        # by hand, stacks up
    DAG task 7 golden_questions                      # every day, after refresh_ontology

1. Load `evals/golden/*.yaml` (plus `GOLDEN_EXTRA_DIR`, for a deliberate test question); skip a
   question whose `needs_day` is newer than the snapshot.
2. Ask them one at a time through the `ask` client, so each answer's model calls can be linked by
   caller key and time window (llm/ask.py).
3. Run the reference SQL and the answer's own SQL on the same snapshot, read-only and without
   file access, and score `golden_verdict` (exact_match, within_tolerance, wrong, refused) and
   `sql_consistent`.
4. Write one answer trace per question with both scores, one `golden_run` trace, and put every
   `wrong`, `refused` or inconsistent answer in the annotation queue `answer-review`.
5. Write data/artifacts/<ds>/golden.json for record_run.

Exit 0 when no answer is wrong, 1 when one is (or the run could not be scored), 99 (Airflow marks
the task skipped) when Auto Ontology is not reachable or the run is told to skip.
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime as dtm
import json
import os
import sys
import threading
import time
import uuid
from pathlib import Path

import duckdb
import yaml

from llm import ask as ak
from llm.observe import Langfuse, Span, new_trace_id, read_env
from publish.artifacts import ARTIFACTS, day_dir, write_json

GOLDEN_DIR = Path("evals/golden")
SKIP = 99
VERDICTS = ("exact_match", "within_tolerance", "wrong", "refused")
QUEUE_VERDICTS = ("wrong", "refused")
MAX_ANSWER_ROWS = 20          # a scalar answered with a whole table is not an answer
SQL_TIMEOUT_S = 60


@dataclasses.dataclass
class Question:
    id: str
    question: str
    reference_sql: str
    kind: str = "scalar"
    key: str | None = None
    tolerance_pct: float = 0.0
    needs_day: str | None = None
    evidence: list[str] = dataclasses.field(default_factory=list)
    source: str = ""


def load_questions(*dirs: Path) -> list[Question]:
    out = []
    for d in dirs:
        for path in sorted(d.glob("g-*.yaml")) if d and d.is_dir() else []:
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
            doc["needs_day"] = str(doc["needs_day"]) if doc.get("needs_day") else None
            out.append(Question(**doc, source=str(path)))
    return out


# --- SQL on the snapshot ---------------------------------------------------------------------

def connect(snapshot: Path) -> duckdb.DuckDBPyConnection:
    """Read-only, and no file or network access: the answer's SQL is written by a model."""
    con = duckdb.connect(str(snapshot), read_only=True)
    con.execute("set enable_external_access = false")
    con.execute("set lock_configuration = true")
    return con


def run_sql(con: duckdb.DuckDBPyConnection, sql: str, timeout_s: int = SQL_TIMEOUT_S):
    """(columns, rows) of one statement; a statement running past the timeout is interrupted."""
    timer = threading.Timer(timeout_s, con.interrupt)
    timer.start()
    try:
        cur = con.execute(sql.strip().rstrip(";"))
        cols = [d[0] for d in cur.description or []]
        return cols, cur.fetchall()
    finally:
        timer.cancel()


def snapshot_day(con: duckdb.DuckDBPyConnection) -> str | None:
    row = con.execute("select max(revenue_date) from data_mart_layer.rpt__finance__revenue__daily").fetchone()
    return str(row[0]) if row and row[0] else None


# --- scoring ---------------------------------------------------------------------------------

def compare(expected: float, got: float, tolerance_pct: float) -> str:
    diff = abs(got - expected)
    exact = diff < 0.5 if float(expected).is_integer() else diff <= 1e-9 * max(1.0, abs(expected))
    if exact:
        return "exact_match"
    if diff <= tolerance_pct / 100 * abs(expected):
        return "within_tolerance"
    return "wrong"


def best(verdicts: list[str]) -> str:
    return min(verdicts, key=VERDICTS.index) if verdicts else "wrong"


def worst(verdicts: list[str]) -> str:
    return max(verdicts, key=VERDICTS.index) if verdicts else "wrong"


def scalar_value(rows: list[dict], ref_col: str) -> tuple[float | None, str]:
    """The one value a scalar answer states: one row, and in it either a single number or the
    number whose column name matches the reference column. Anything else is ambiguous, so an
    unrelated number that happens to match cannot pass a wrong answer (review on #27)."""
    if len(rows) != 1:
        return None, f"{len(rows)} rows answer a one-value question"
    nums = {k: n[0] for k, v in rows[0].items() if len(n := ak.numbers_in(v)) == 1}
    if len(nums) == 1:
        return next(iter(nums.values())), ""
    ref = ref_col.lower()
    named = [n for k, n in nums.items() if k.lower() == ref or k.lower() in ref or ref in k.lower()]
    if len(named) == 1:
        return named[0], ""
    return None, f"ambiguous: {len(nums)} numbers ({', '.join(nums)}) and none named like {ref_col}"


def key_column(rows: list[dict], key: str, keys: set[str]) -> str | None:
    """The answer's column that names a row: the reference key column, else the first column
    whose values hold every reference key."""
    cols = list(rows[0])
    if key in cols:
        return key
    for c in cols:
        if keys <= {str(r.get(c)).strip().lower() for r in rows}:
            return c
    return None


def score_answer(q: Question, ref_cols: list[str], ref_rows: list[tuple],
                 rows: list[dict] | None) -> tuple[str, str]:
    """(golden_verdict, reason). No rows is `refused`. `scalar` compares the one value the answer
    states (`scalar_value`); `rows` needs exactly the reference keys, each once, and each
    reference number in its row."""
    if not rows or not ak.numbers_in(rows):
        return "refused", "the answer has no rows with a number"
    if len(rows) > MAX_ANSWER_ROWS:
        return "wrong", f"{len(rows)} rows answer a question that needs {len(ref_rows)}"
    if not ref_rows:
        return "wrong", "the reference SQL returned no row"
    if q.kind == "scalar":
        expected = float(ref_rows[0][0])
        got, why = scalar_value(rows, ref_cols[0])
        if got is None:
            return "wrong", f"expected {expected:,.2f}; {why}"
        return compare(expected, got, q.tolerance_pct), f"expected {expected:,.2f}; answer {got:,.2f}"
    ki = ref_cols.index(q.key)
    ref_keys = [str(r[ki]).strip().lower() for r in ref_rows]
    col = key_column(rows, q.key, set(ref_keys))
    if col is None:
        return "wrong", f"no column of the answer names every {q.key} of the reference"
    by_key: dict[str, list[dict]] = {}
    for r in rows:
        by_key.setdefault(str(r.get(col)).strip().lower(), []).append(r)
    extra = sorted(set(by_key) - set(ref_keys))
    dupes = sorted(k for k, v in by_key.items() if len(v) > 1)
    missing = sorted(set(ref_keys) - set(by_key))
    if extra or dupes or missing:
        return "wrong", "; ".join(f"{label}: {', '.join(ks)}" for label, ks in
                                  (("missing", missing), ("extra", extra), ("duplicate", dupes)) if ks)
    per_key, reasons = [], []
    for ref, key in zip(ref_rows, ref_keys):
        got = ak.numbers_in({k: v for k, v in by_key[key][0].items() if k != col})
        vs = [best([compare(float(e), n, q.tolerance_pct) for n in got])
              for i, e in enumerate(ref) if i != ki and isinstance(e, (int, float))]
        per_key.append(worst(vs))
        if per_key[-1] == "wrong":
            reasons.append(f"{ref[ki]}: expected {[e for i, e in enumerate(ref) if i != ki]}, got {got}")
    return worst(per_key), "; ".join(reasons) or f"{len(ref_rows)} row(s) matched"


def sql_consistent(con: duckdb.DuckDBPyConnection, sql: str | None, rows: list[dict] | None) -> tuple[bool | None, str]:
    """Does the answer's own SQL, re-run on the snapshot, give the numbers the answer stated?
    None when the answer has no SQL."""
    if not sql:
        return None, "no SQL in the answer"
    try:
        _, got = run_sql(con, sql)
    except duckdb.Error as e:
        return False, f"the answer's SQL fails on the snapshot: {str(e).splitlines()[0][:160]}"
    rerun = sorted(round(n, 4) for n in ak.numbers_in([list(r) for r in got]))
    stated = sorted(round(n, 4) for n in ak.numbers_in(rows or []))
    if rerun == stated:
        return True, f"{len(got)} row(s) reproduced"
    return False, f"re-run gives {rerun[:6]}, the answer stated {stated[:6]}"


# --- run -------------------------------------------------------------------------------------

@dataclasses.dataclass
class Result:
    q: Question
    answer: ak.Answer
    verdict: str
    reason: str
    consistent: bool | None
    consistency_reason: str
    expected: list

    @property
    def queued(self) -> bool:
        return self.verdict in QUEUE_VERDICTS or self.consistent is False


def score_events(r: Result, configs: dict[str, dict]) -> list[dict]:
    tid = r.answer.trace_id
    ev = [{"type": "score-create", "body": {
        "id": str(uuid.uuid4()), "traceId": tid, "name": "golden_verdict", "value": r.verdict,
        "dataType": "CATEGORICAL", "configId": configs["golden_verdict"]["id"], "comment": r.reason[:500]}}]
    if r.consistent is not None:
        ev.append({"type": "score-create", "body": {
            "id": str(uuid.uuid4()), "traceId": tid, "name": "sql_consistent", "value": 1 if r.consistent else 0,
            "dataType": "BOOLEAN", "configId": configs["sql_consistent"]["id"],
            "comment": r.consistency_reason[:500]}})
    return ev


def summarise(results: list[Result]) -> dict:
    counts = {v: sum(1 for r in results if r.verdict == v) for v in VERDICTS}
    return {"counts": counts, "asked": len(results),
            "inconsistent": sum(1 for r in results if r.consistent is False),
            "queued": sum(1 for r in results if r.queued),
            "cost_usd": round(sum(r.answer.calls.get("cost_usd") or 0 for r in results), 6),
            "call_count": sum(r.answer.calls.get("call_count") or 0 for r in results)}


def report_doc(ds: str, run_id: str, status: str, **extra) -> dict:
    return {"ds": ds, "run_id": run_id, "status": status,
            "finished_at": ak.iso(dtm.datetime.now(dtm.UTC)), **extra}


def run(ds: str, run_id: str, dirs: list[Path], snapshot: Path, artifacts: Path) -> int:
    out = day_dir(ds, artifacts) / "golden.json"
    env = read_env()
    try:
        session = ak.sign_in(env)
    except OSError as e:                       # connection refused, unknown host: profile down
        write_json(out, report_doc(ds, run_id, "skipped", reason=f"Auto Ontology unreachable: {e}"))
        print(f"[golden] Auto Ontology is not reachable ({e}); skipped")
        return SKIP
    lf = Langfuse(env)
    configs = lf.score_configs()
    queue_id = lf.queue_id()
    ak.wait_for_compile(session)

    con = connect(snapshot)
    try:
        day = snapshot_day(con)
        questions = load_questions(*dirs)
        ready = [q for q in questions if not q.needs_day or (day and q.needs_day <= day)]
        print(f"[golden] {ds}: snapshot ends {day}; {len(ready)} of {len(questions)} question(s) asked")
        refs, answers = {}, []
        for q in ready:
            refs[q.id] = run_sql(con, q.reference_sql)
            a = ak.ask(session, q.question)
            answers.append(a)
            print(f"[golden] {q.id}: {int((a.finished - a.started).total_seconds())}s"
                  + (f", error {a.error}" if a.error else ""))
        time.sleep(ak.INGEST_WAIT_S)
        ak.link_calls(answers, env, lf)
        results = []
        for q, a in zip(ready, answers):
            cols, rows = refs[q.id]
            verdict, reason = score_answer(q, cols, rows, a.rows)
            if a.error:
                verdict, reason = "refused", f"chat error: {a.error}"
            consistent, creason = sql_consistent(con, a.sql, a.rows)
            results.append(Result(q, a, verdict, reason, consistent, creason, [list(r) for r in rows]))
    finally:
        con.close()

    session_id = f"golden:{ds}:{run_id}"
    snap = ak.snapshot_hash(snapshot)
    spans, scores = [], []
    for r in results:
        spans += ak.answer_spans(
            r.answer, session_id=session_id, snapshot=snap,
            tags=["job:golden", "caller:golden-runner", f"golden:{r.q.id}", f"verdict:{r.verdict}"],
            extra={"golden_id": r.q.id, "reference_sql": r.q.reference_sql, "expected_rows": r.expected,
                   "golden_verdict": r.verdict, "verdict_reason": r.reason,
                   "sql_consistent": r.consistent, "consistency_reason": r.consistency_reason,
                   "ds": ds, "run_id": run_id})
        scores += score_events(r, configs)
    summary = summarise(results)
    now = dtm.datetime.now(dtm.UTC)
    run_trace = new_trace_id()
    spans.append(Span(run_trace, "golden_run", min((r.answer.started for r in results), default=now), now,
                      ak.trace_attrs(name="golden_run", session_id=session_id, tags=["job:golden"],
                                     input={"ds": ds, "run_id": run_id, "snapshot_day": day, "snapshot_hash": snap},
                                     output={**summary, "questions": {r.q.id: r.verdict for r in results}},
                                     metadata={"answer_trace_ids": {r.q.id: r.answer.trace_id for r in results}})))
    lf.export_spans(spans)
    if scores:
        lf.ingest(scores)
    for r in results:
        if r.queued:
            lf.enqueue(queue_id, r.answer.trace_id)

    status = "failed" if summary["counts"]["wrong"] else "passed"
    write_json(out, report_doc(ds, run_id, status, snapshot_day=day, snapshot_hash=snap,
                               run_trace_id=run_trace, session_id=session_id, **summary,
                               questions=[{"id": r.q.id, "verdict": r.verdict, "reason": r.reason,
                                           "sql_consistent": r.consistent, "queued": r.queued,
                                           "answer": r.answer.text[:200], "sql": r.answer.sql,
                                           "trace_id": r.answer.trace_id,
                                           "cost_usd": r.answer.calls.get("cost_usd"),
                                           "call_count": r.answer.calls.get("call_count")}
                                          for r in results]))
    for r in results:
        print(f"[golden] {r.q.id} {r.verdict}{' (queued)' if r.queued else ''}: {r.reason}; "
              f"sql_consistent={r.consistent}; {r.answer.calls.get('call_count')} call(s) "
              f"${r.answer.calls.get('cost_usd') or 0:.6f}; trace {r.answer.trace_id}")
    c = summary["counts"]
    print(f"[golden] {status}: {c['exact_match']} exact, {c['within_tolerance']} within tolerance, "
          f"{c['wrong']} wrong, {c['refused']} refused; {summary['queued']} queued in answer-review; "
          f"{summary['call_count']} linked call(s), ${summary['cost_usd']:.6f}; session {session_id}")
    return 1 if status == "failed" else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ds", required=True)
    ap.add_argument("--run-id", default="manual")
    ap.add_argument("--enabled", default="true", help="false skips (the backfill asks only on its last day)")
    ap.add_argument("--snapshot", type=Path, default=ak.SNAPSHOT)
    args = ap.parse_args(argv)
    if args.enabled.strip().lower() in ("false", "0", "no"):
        write_json(day_dir(args.ds, ARTIFACTS) / "golden.json",
                   report_doc(args.ds, args.run_id, "skipped", reason="disabled for this run"))
        print("[golden] disabled for this run; skipped")
        return SKIP
    extra = os.environ.get("GOLDEN_EXTRA_DIR")
    dirs = [GOLDEN_DIR] + ([Path(extra)] if extra else [])
    try:
        return run(args.ds, args.run_id, dirs, args.snapshot, ARTIFACTS)
    except (ak.AskError, RuntimeError, OSError, duckdb.Error) as e:
        write_json(day_dir(args.ds, ARTIFACTS) / "golden.json",
                   report_doc(args.ds, args.run_id, "error", reason=str(e)[:300]))
        print(f"[golden] FAIL: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
