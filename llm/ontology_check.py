"""ontology-check: Auto Ontology answers from the snapshot, and every model call is in the gateway log.

    make ontology-check        # with the obs and ontology profiles up and a snapshot published

1. Sign in to Auto Ontology through its web front door (the backend port is never published)
   and wait until no semantic compile is running and one has succeeded.
2. Ask a revenue question and read the answer's rows. The chat is an LLM agent and now and then
   ends a run without SQL (seen once in M9), so it gets up to --attempts tries; the output says
   how many it took.
3. Compute the same number with SQL on the published snapshot; they must match.
4. Read the gateway's spend log for the question's time window: every call made with the
   `auto-ontology` key is listed with model and cost, and Langfuse holds one generation per call.
5. Prove there is no other way out: from both Auto Ontology containers, the internet is
   unreachable while the gateway is reachable.

Prints counts, costs and the comparison; never a key. Exit 1 if any step fails.
"""
from __future__ import annotations

import argparse
import datetime as dtm
import json
import subprocess
import sys
import time
from pathlib import Path

import duckdb

from llm.ask import (AskError, Session, chat, numbers_in, sign_in,  # noqa: F401 (tests use them)
                     wait_for_compile)
from llm.observe import (Langfuse, caller_of, generation_key_alias, read_env,  # noqa: F401
                         spend_logs)

SNAPSHOT = Path("data/serve/analytics.duckdb")
CALLER = "auto-ontology"
CONTAINERS = ("wh-auto-ontology-1", "wh-ingestion-service-1")
DEFAULT_DAY = "2026-01-05"


def ask(session: Session, question: str) -> dict:
    try:
        return chat(session, question)
    except AskError as e:
        raise SystemExit(f"[ontology-check] FAIL: {e}") from None


def expected_net_revenue(day: str, snapshot: Path = SNAPSHOT) -> int:
    con = duckdb.connect(str(snapshot), read_only=True)
    try:
        row = con.execute("select net_revenue_idr from data_mart_layer.rpt__finance__revenue__daily "
                          "where revenue_date = ?::date", [day]).fetchone()
    finally:
        con.close()
    if row is None:
        raise SystemExit(f"[ontology-check] FAIL: the snapshot has no revenue row for {day}")
    return int(row[0])


def answer_matches(answer: dict, expected: int, tolerance: float = 1.0) -> bool:
    return any(abs(n - expected) <= tolerance for n in numbers_in(answer.get("sql_response_from_db")))


def egress_blocked(container: str) -> tuple[bool, str]:
    code = ("import socket, urllib.request\n"
            "s = socket.socket(); s.settimeout(5)\n"
            "try:\n    s.connect(('1.1.1.1', 443)); out = 'internet reachable'\n"
            "except OSError as e:\n    out = 'internet unreachable'\n"
            "try:\n    urllib.request.urlopen('http://llm-gateway:4000/health/liveliness', timeout=5); out += ', gateway reachable'\n"
            "except Exception:\n    out += ', gateway unreachable'\n"
            "print(out)")
    res = subprocess.run(["docker", "exec", container, "python", "-c", code], capture_output=True, text=True, timeout=60)
    out = res.stdout.strip()
    return out == "internet unreachable, gateway reachable", out or res.stderr.strip()[:120]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--day", default=DEFAULT_DAY, help="the day to ask about (in the snapshot)")
    ap.add_argument("--attempts", type=int, default=2, help="tries before the answer counts as wrong")
    args = ap.parse_args(argv)
    env = read_env()
    ok = True
    try:
        session = sign_in(env)
        status = wait_for_compile(session)
    except AskError as e:
        raise SystemExit(f"[ontology-check] FAIL: {e}") from None
    print(f"[ontology-check] compile ok: last success {status.get('last_success_at')}")

    question = f"What was the net revenue on {args.day}?"
    expected = expected_net_revenue(args.day)
    started = dtm.datetime.now(dtm.UTC)
    for attempt in range(1, args.attempts + 1):
        answer = ask(session, question)
        matched = answer_matches(answer, expected)
        if matched:
            break
    finished = dtm.datetime.now(dtm.UTC)
    ok &= matched
    print(f"[ontology-check] {'answer ok' if matched else 'FAIL answer'} (attempt {attempt} of "
          f"{args.attempts}): {question!r} -> rows {json.dumps(answer.get('sql_response_from_db'))[:160]}; "
          f"snapshot SQL says {expected:,}")
    print(f"[ontology-check] answer: {' '.join(str(answer.get('response', '')).split())[:300]}")
    print(f"[ontology-check] sql: {' '.join(str(answer.get('sql_code', '')).split())[:300]}")

    time.sleep(20)                                   # spend log and traces are written async
    window = (started - dtm.timedelta(seconds=5), finished + dtm.timedelta(seconds=20))
    logs = spend_logs(f"sk-{env['LITELLM_MASTER_SECRET']}", *window)
    ours = [r for r in logs if caller_of(r) == CALLER]
    others = [r for r in logs if caller_of(r) not in (CALLER, None)]
    cost = sum(float(r.get("spend") or 0) for r in ours)
    models = sorted({str(r.get("model_group") or r.get("model")) for r in ours})
    gens = [g for g in Langfuse(env).generations(*window) if generation_key_alias(g) == CALLER]
    calls_ok = len(ours) > 0 and len(gens) >= len(ours)
    ok &= calls_ok
    print(f"[ontology-check] {'gateway ok' if calls_ok else 'FAIL gateway'}: {len(ours)} call(s) with the "
          f"{CALLER} key in the gateway spend log ({', '.join(models)}; ${cost:.6f}); "
          f"{len(gens)} matching Langfuse generation(s); {len(others)} call(s) by other callers in the window")

    for c in CONTAINERS:
        blocked, detail = egress_blocked(c)
        ok &= blocked
        print(f"[ontology-check] {'egress ok' if blocked else 'FAIL egress'}: {c}: {detail}")
    print(f"[ontology-check] {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
