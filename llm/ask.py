"""ask: put one question to Auto Ontology and keep a full answer trace in Langfuse (PLAN 8.2).

    make ask Q="What was the net revenue on 2026-01-05?"

1. Sign in through Auto Ontology's web front door (the backend port is never published) and
   stream one chat answer: text, SQL, rows, step trace.
2. Link the model calls behind that answer. Auto Ontology cannot forward a request id to its
   model client (docs/m0-findings.md item 6), so the calls are the ones made with the
   `auto-ontology` key while the answer ran (caller key + time window). Questions asked in the
   web UI during the same window are counted too; the trace says how it was linked.
3. Write one Langfuse trace `ask`: question, answer, SQL, rows, step trace, snapshot hash,
   conversation id, the linked calls' count, tokens and cost, and their Langfuse generation ids.

The golden runner (`llm/golden.py`) uses the same functions. Prints no key.
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime as dtm
import hashlib
import http.cookiejar
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from llm.observe import (Langfuse, Span, calls_summary, generation_key_alias, iso, new_trace_id,
                         parse_time, read_env, spend_logs)

# APP_URL: the only origin Auto Ontology's auth trusts. From a container the edge is reached by
# its service name (AO_URL) while Host and Origin still say localhost:3000.
APP_ORIGIN = "http://localhost:3000"
AO = os.environ.get("AO_URL", APP_ORIGIN)
SNAPSHOT = Path("data/serve/analytics.duckdb")
AO_CALLER = "auto-ontology"             # the key Auto Ontology's own model calls carry
LINK_METHOD = "caller_key+time_window"
INGEST_WAIT_S = 20                      # spend log and Langfuse are written asynchronously
WINDOW_PAD = (dtm.timedelta(seconds=2), dtm.timedelta(seconds=10))
MAX_ROWS_KEPT = 50


class AskError(RuntimeError):
    """The chat answered with an error event or ended without a result."""


class Session:
    """A signed-in Auto Ontology session (cookie jar), as the web UI would hold."""

    def __init__(self, email: str, password: str, base: str = AO):
        self.base = base.rstrip("/")
        self.host = urllib.parse.urlsplit(APP_ORIGIN).netloc
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        status, _ = self.call("POST", "/api/auth/sign-in/email", {"email": email, "password": password})
        if status != 200:
            raise AskError(f"sign-in failed: HTTP {status}")

    def _request(self, method: str, path: str, body: dict | None, accept: str) -> urllib.request.Request:
        return urllib.request.Request(
            self.base + path, method=method, data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json", "Origin": APP_ORIGIN, "Host": self.host,
                     "Accept": accept})

    def call(self, method: str, path: str, body: dict | None = None, timeout: int = 60):
        try:
            with self.opener.open(self._request(method, path, body, "application/json"), timeout=timeout) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def stream(self, path: str, body: dict, timeout: int = 900):
        with self.opener.open(self._request("POST", path, body, "text/event-stream"), timeout=timeout) as resp:
            for raw in resp:
                line = raw.decode("utf-8", "replace").strip()
                if line.startswith("data:"):
                    payload = line.removeprefix("data:").strip()
                    if payload == "[DONE]":
                        return
                    yield json.loads(payload)


def sign_in(env: dict[str, str]) -> Session:
    return Session("admin@example.com", env["AO_ADMIN_SECRET"])


def wait_for_compile(session: Session, timeout_s: int = 3600) -> dict:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        status, body = session.call("GET", "/api/semantic-compilation/status")
        doc = json.loads(body or b"{}") if status == 200 else {}
        if doc and not doc.get("running") and doc.get("last_success_at"):
            return doc
        time.sleep(15)
    raise AskError("semantic compile did not finish")


def chat(session: Session, question: str, calculation_only: bool = False,
         request_id: str | None = None) -> dict:
    """One chat answer: the `answer` of the stream's `result` event. `calculation_only` answers
    with SQL only (overlay patch 0002): the agent is not offered the catalog view, whose tables
    never come into view for run_sql (issue 34)."""
    body = {"question": question, **({"calculation_only": True} if calculation_only else {}),
            **({"request_id": request_id} if request_id else {})}
    for event in session.stream("/api/chat/completions", body):
        if event.get("type") == "result":
            return event["answer"]
        if event.get("type") == "error":
            raise AskError(f"chat error: {event.get('message')}")
    raise AskError("the chat stream ended without a result")


def answer_rows(value) -> list[dict] | None:
    """The answer's rows as a list of dicts. Auto Ontology sends them as a list holding a JSON
    string (`["[{\"net_revenue_idr\": 718545885.0}]"]`, seen in M9); None when there are none."""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            return answer_rows(json.loads(value))
        except ValueError:
            return None
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        out: list[dict] = []
        for item in value:
            if isinstance(item, dict):
                out.append(item)
            elif isinstance(item, (str, list)):
                out += answer_rows(item) or []
        return out
    return None


def numbers_in(value) -> list[float]:
    """Every number in a value (rows, dicts, JSON strings); booleans are not numbers."""
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


@dataclasses.dataclass
class Answer:
    question: str
    started: dtm.datetime
    finished: dtm.datetime
    text: str = ""
    sql: str | None = None
    rows: list[dict] | None = None
    thoughts: object = None
    conversation_id: str | None = None
    error: str | None = None
    raw_keys: list[str] = dataclasses.field(default_factory=list)
    trace_id: str = dataclasses.field(default_factory=new_trace_id)
    calls: dict = dataclasses.field(default_factory=dict)
    generation_ids: list[str] = dataclasses.field(default_factory=list)
    link_method: str = LINK_METHOD

    @property
    def window(self) -> tuple[dtm.datetime, dtm.datetime]:
        return self.started - WINDOW_PAD[0], self.finished + WINDOW_PAD[1]


def ask(session: Session, question: str, calculation_only: bool = False) -> Answer:
    """Ask once; a chat error becomes `Answer.error` instead of an exception. The answer's trace
    id goes along as `request_id` (overlay patch 0003), so every model call Auto Ontology makes
    for it is tagged `answer:<trace id>` in the gateway (issue 36)."""
    started = dtm.datetime.now(dtm.UTC)
    trace_id = new_trace_id()
    try:
        raw = chat(session, question, calculation_only, request_id=trace_id)
    except (AskError, OSError, ValueError) as e:
        return Answer(question, started, dtm.datetime.now(dtm.UTC), error=str(e)[:300], trace_id=trace_id)
    sql = raw.get("sql_code")
    return Answer(
        question, started, dtm.datetime.now(dtm.UTC),
        text=str(raw.get("response") or ""),
        sql=str(sql) if sql else None,
        rows=answer_rows(raw.get("sql_response_from_db")),
        thoughts=raw.get("thoughts"),
        conversation_id=raw.get("conversation_id") or raw.get("chat_id"),
        raw_keys=sorted(raw), trace_id=trace_id)


def owner_of(t: dtm.datetime, answers: list[Answer]) -> Answer | None:
    """The one answer a call at time t belongs to: among the answers whose padded window holds t,
    the one that started last before t (else the earliest). The padded windows of back-to-back
    questions overlap, so a call is never counted for two answers (review on #33)."""
    holding = [a for a in answers if a.window[0] <= t <= a.window[1]]
    if not holding:
        return None
    started = [a for a in holding if a.started <= t]
    return max(started, key=lambda a: a.started) if started else min(holding, key=lambda a: a.started)


def request_tag(a: Answer) -> str:
    return f"answer:{a.trace_id}"


def tagged_with(row: dict, tag: str) -> bool:
    """A spend-log row or Langfuse generation that carries the answer's tag (patch 0003)."""
    tags = row.get("request_tags")
    if isinstance(tags, str):
        try:
            tags = json.loads(tags)
        except ValueError:
            tags = [tags]
    if isinstance(tags, list) and tag in tags:
        return True
    return tag in json.dumps(row.get("metadata") or {}, default=str)


def link_calls(answers: list[Answer], env: dict[str, str], lf: Langfuse) -> None:
    """Attach to each answer the `auto-ontology` calls made for it. Calls tagged with the answer's
    request id (overlay patch 0003) are exact; an answer without any tagged call falls back to its
    time window, a call in two padded windows going to one answer (`owner_of`). One read of each
    source for all answers; `link_method` says which way each answer was linked."""
    if not answers:
        return
    since = min(a.window[0] for a in answers)
    until = max(a.window[1] for a in answers)
    logs = spend_logs(f"sk-{env['LITELLM_MASTER_SECRET']}", since, until)
    gens = [g for g in lf.generations(since, until) if generation_key_alias(g) == AO_CALLER]
    rows: dict[int, list[dict]] = {id(a): [] for a in answers}
    ids: dict[int, list[str]] = {id(a): [] for a in answers}
    tagged = {id(a): [r for r in logs if tagged_with(r, request_tag(a))] for a in answers}
    claimed = {id(r) for rs in tagged.values() for r in rs}
    for r in logs:
        if id(r) not in claimed and (a := owner_of(parse_time(r.get("startTime")), answers)) and not tagged[id(a)]:
            rows[id(a)].append(r)
    for g in gens:
        a = next((a for a in answers if tagged_with(g, request_tag(a))), None)
        if a is None and (a := owner_of(parse_time(g.get("startTime")), answers)) and tagged[id(a)]:
            a = None                              # a tagged answer takes tagged generations only
        if a is not None:
            ids[id(a)].append(g["id"])
    for a in answers:
        a.link_method = "request_id" if tagged[id(a)] else LINK_METHOD
        a.calls = calls_summary(tagged[id(a)] or rows[id(a)], AO_CALLER)
        a.generation_ids = ids[id(a)]


def snapshot_hash(path: Path = SNAPSHOT) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _clip(value, limit: int = 4000):
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    return text if len(text) <= limit else text[:limit] + " ...[clipped]"


def trace_attrs(*, name: str, session_id: str | None, tags: list[str], input, output, metadata: dict) -> dict:
    """Langfuse's OTLP attributes for the trace a root span stands for."""
    attrs = {"langfuse.trace.name": name, "langfuse.session.id": session_id, "langfuse.trace.tags": tags,
             "langfuse.trace.input": input, "langfuse.trace.output": output,
             "langfuse.observation.input": input, "langfuse.observation.output": output}
    attrs.update({f"langfuse.trace.metadata.{k}": v for k, v in metadata.items()})
    return attrs


def answer_spans(a: Answer, *, session_id: str | None, tags: list[str], snapshot: str | None,
                 extra: dict | None = None) -> list[Span]:
    """One answer trace `ask` (root span) and its chat span."""
    link = {"method": a.link_method, "caller": AO_CALLER, "request_tag": request_tag(a), "window_start": iso(a.window[0]),
            "window_end": iso(a.window[1]), **a.calls, "generation_ids": a.generation_ids,
            "note": ("request_id: every call carried the answer's tag answer:<trace id> (overlay "
                     "patch 0003); caller_key+time_window: no tagged call, so calls of the "
                     "auto-ontology key in the answer's window, web UI questions included")}
    output = {"answer": a.text, "sql": a.sql, "rows": (a.rows or [])[:MAX_ROWS_KEPT],
              "row_count": None if a.rows is None else len(a.rows), "error": a.error}
    meta = {"snapshot_hash": snapshot, "conversation_id": a.conversation_id, "finished_at": iso(a.finished),
            "cost_usd": a.calls.get("cost_usd"), "call_count": a.calls.get("call_count"),
            "linked_calls": link, "answer_keys": a.raw_keys, **(extra or {})}
    root = Span(a.trace_id, "ask", a.started, a.finished,
                trace_attrs(name="ask", session_id=session_id, tags=tags,
                            input={"question": a.question}, output=output, metadata=meta))
    chat_span = Span(a.trace_id, "auto-ontology chat", a.started, a.finished, {
        "langfuse.observation.type": "span",
        "langfuse.observation.input": {"question": a.question},
        "langfuse.observation.output": {"thoughts": _clip(a.thoughts), "sql": a.sql},
        "langfuse.observation.metadata.linked_calls": link,
        "langfuse.observation.level": "ERROR" if a.error else "DEFAULT",
        "langfuse.observation.status_message": a.error}, parent_id=root.span_id)
    return [root, chat_span]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("question", nargs="+")
    args = ap.parse_args(argv)
    env = read_env()
    lf = Langfuse(env)
    session = sign_in(env)
    a = ask(session, " ".join(args.question))
    time.sleep(INGEST_WAIT_S)
    link_calls([a], env, lf)
    lf.export_spans(answer_spans(a, session_id=None, tags=["job:chat", "caller:ask"], snapshot=snapshot_hash()))
    print(f"[ask] {a.text or a.error}")
    print(f"[ask] sql: {' '.join(str(a.sql or '').split())[:300]}")
    print(f"[ask] rows: {json.dumps(a.rows, default=str)[:300]}")
    print(f"[ask] {a.calls.get('call_count')} linked call(s), ${a.calls.get('cost_usd', 0):.6f}; "
          f"trace {a.trace_id}")
    return 1 if a.error else 0


if __name__ == "__main__":
    sys.exit(main())
