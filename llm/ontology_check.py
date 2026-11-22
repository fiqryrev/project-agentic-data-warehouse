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
import base64
import datetime as dtm
import http.cookiejar
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import duckdb

from llm.gateway_smoke import GATEWAY, LANGFUSE, read_env

AO = "http://127.0.0.1:3000"
SNAPSHOT = Path("data/serve/analytics.duckdb")
CALLER = "auto-ontology"
CONTAINERS = ("wh-auto-ontology-1", "wh-ingestion-service-1")
DEFAULT_DAY = "2026-01-05"


class Session:
    """A signed-in Auto Ontology session (cookie jar), as the web UI would hold."""

    def __init__(self, email: str, password: str):
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        status, _ = self.call("POST", "/api/auth/sign-in/email", {"email": email, "password": password})
        if status != 200:
            raise SystemExit(f"[ontology-check] sign-in failed: HTTP {status}")

    def call(self, method: str, path: str, body: dict | None = None, timeout: int = 60):
        req = urllib.request.Request(
            AO + path, method=method, data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json", "Origin": "http://localhost:3000"})
        try:
            with self.opener.open(req, timeout=timeout) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def stream(self, path: str, body: dict, timeout: int = 900):
        req = urllib.request.Request(
            AO + path, method="POST", data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "Origin": "http://localhost:3000",
                     "Accept": "text/event-stream"})
        with self.opener.open(req, timeout=timeout) as resp:
            for raw in resp:
                line = raw.decode("utf-8", "replace").strip()
                if line.startswith("data:"):
                    payload = line.removeprefix("data:").strip()
                    if payload == "[DONE]":
                        return
                    yield json.loads(payload)


def wait_for_compile(session: Session, timeout_s: int = 3600) -> dict:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        status, body = session.call("GET", "/api/semantic-compilation/status")
        doc = json.loads(body or b"{}") if status == 200 else {}
        if doc and not doc.get("running") and doc.get("last_success_at"):
            return doc
        time.sleep(15)
    raise SystemExit("[ontology-check] FAIL: semantic compile did not finish")


def ask(session: Session, question: str) -> dict:
    for event in session.stream("/api/chat/completions", {"question": question}):
        if event.get("type") == "result":
            return event["answer"]
        if event.get("type") == "error":
            raise SystemExit(f"[ontology-check] FAIL: chat error: {event.get('message')}")
    raise SystemExit("[ontology-check] FAIL: the chat stream ended without a result")


def expected_net_revenue(day: str, snapshot: Path = SNAPSHOT) -> int:
    con = duckdb.connect(str(snapshot), read_only=True)
    try:
        row = con.execute("select net_revenue_idr from mart.rpt__finance__revenue__daily "
                          "where revenue_date = ?::date", [day]).fetchone()
    finally:
        con.close()
    if row is None:
        raise SystemExit(f"[ontology-check] FAIL: the snapshot has no revenue row for {day}")
    return int(row[0])


def numbers_in(value) -> list[float]:
    """Every number in an answer's rows. Auto Ontology sends rows as a list holding a JSON string
    (`["[{\"net_revenue_idr\": 718545885.0}]"]`, seen in M9), so strings are parsed too."""
    if isinstance(value, bool):
        return []
    if isinstance(value, (int, float)):
        return [float(value)]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except ValueError:
            try:
                return [float(value)]
            except ValueError:
                return []
        return numbers_in(parsed) if not isinstance(parsed, str) else []
    if isinstance(value, dict):
        value = list(value.values())
    if isinstance(value, list):
        return [n for v in value for n in numbers_in(v)]
    return []


def answer_matches(answer: dict, expected: int, tolerance: float = 1.0) -> bool:
    return any(abs(n - expected) <= tolerance for n in numbers_in(answer.get("sql_response_from_db")))


def spend_logs(master: str, since: dtm.datetime, until: dtm.datetime) -> list[dict]:
    # With a date range the API sums spend per key unless summarize=false (seen in M9).
    q = (f"summarize=false&start_date={since.date().isoformat()}"
         f"&end_date={(until + dtm.timedelta(days=1)).date().isoformat()}")
    req = urllib.request.Request(f"{GATEWAY}/spend/logs?{q}", headers={"Authorization": f"Bearer {master}"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        rows = json.loads(resp.read())
    return [r for r in rows if since <= parse_time(r.get("startTime")) <= until]


def parse_time(value) -> dtm.datetime:
    t = dtm.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=dtm.UTC)


def caller_of(row: dict) -> str | None:
    meta = row.get("metadata") or {}
    if isinstance(meta, str):
        meta = json.loads(meta or "{}")
    return meta.get("user_api_key_alias")


def langfuse_generations(env: dict, since: dtm.datetime, until: dtm.datetime) -> list[dict]:
    """Generations in [since, until]. Without an upper bound Langfuse 4.83 answers 422 "narrow your
    request" once the project holds a compile's worth of traces (seen in M9)."""
    pk, sk = f"pk-lf-{env['LANGFUSE_PROJECT_PUBLIC_SECRET']}", f"sk-lf-{env['LANGFUSE_PROJECT_SECRET']}"
    auth = base64.b64encode(f"{pk}:{sk}".encode()).decode()
    out, cursor = [], None
    while True:
        url = (f"{LANGFUSE}/api/public/v2/observations?type=GENERATION&limit=50&fields=core,basic,metadata"
               f"&fromStartTime={since.strftime('%Y-%m-%dT%H:%M:%SZ')}"
               f"&toStartTime={until.strftime('%Y-%m-%dT%H:%M:%SZ')}" + (f"&cursor={cursor}" if cursor else ""))
        req = urllib.request.Request(url, headers={"Authorization": f"Basic {auth}"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            page = json.loads(resp.read())
        out += page.get("data") or []
        cursor = (page.get("meta") or {}).get("cursor")
        if not cursor:
            return out


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
    session = Session("admin@example.com", env["AO_ADMIN_SECRET"])
    status = wait_for_compile(session)
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
    gens = [g for g in langfuse_generations(env, *window)
            if (g.get("metadata") or {}).get("attributes.litellm.key_alias") == CALLER]
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
