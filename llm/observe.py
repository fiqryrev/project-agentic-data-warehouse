"""Read the gateway's spend log and Langfuse; write answer traces, scores and queue items to Langfuse.

Shared by the `ask` client, the golden runner and ontology-check. Addresses default to the host
(127.0.0.1); inside the Airflow containers `GATEWAY_URL` and `LANGFUSE_URL` point at the services.
Keys come from `.env` (`read_env`); nothing here prints one.
"""
from __future__ import annotations

import base64
import dataclasses
import datetime as dtm
import json
import os
import urllib.error
import urllib.request
import uuid
from pathlib import Path

GATEWAY = os.environ.get("GATEWAY_URL", "http://127.0.0.1:4000")
LANGFUSE = os.environ.get("LANGFUSE_URL", "http://127.0.0.1:3001")
QUEUE = "answer-review"                 # infra/langfuse/scores.yaml


def read_env(path: Path = Path(".env")) -> dict[str, str]:
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines() if path.exists() else []:
        if "=" in line and not line.lstrip().startswith("#"):
            key, _, value = line.partition("=")
            out[key.strip()] = value.strip()
    return out


def iso(t: dtm.datetime) -> str:
    return t.astimezone(dtm.UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def parse_time(value) -> dtm.datetime:
    t = dtm.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=dtm.UTC)


# --- gateway ---------------------------------------------------------------------------------

def spend_logs(master: str, since: dtm.datetime, until: dtm.datetime) -> list[dict]:
    """Every gateway call that started in [since, until]."""
    # With a date range the API sums spend per key unless summarize=false (seen in M9).
    q = (f"summarize=false&start_date={since.date().isoformat()}"
         f"&end_date={(until + dtm.timedelta(days=1)).date().isoformat()}")
    req = urllib.request.Request(f"{GATEWAY}/spend/logs?{q}", headers={"Authorization": f"Bearer {master}"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        rows = json.loads(resp.read())
    return [r for r in rows if since <= parse_time(r.get("startTime")) <= until]


def caller_of(row: dict) -> str | None:
    meta = row.get("metadata") or {}
    if isinstance(meta, str):
        meta = json.loads(meta or "{}")
    return meta.get("user_api_key_alias")


def calls_summary(rows: list[dict], caller: str) -> dict:
    """The calls one caller key made in a window: count, tokens, cost, models, request ids."""
    ours = [r for r in rows if caller_of(r) == caller]
    return {
        "call_count": len(ours),
        "cost_usd": round(sum(float(r.get("spend") or 0) for r in ours), 8),
        "prompt_tokens": sum(int(r.get("prompt_tokens") or 0) for r in ours),
        "completion_tokens": sum(int(r.get("completion_tokens") or 0) for r in ours),
        "models": sorted({str(r.get("model_group") or r.get("model")) for r in ours}),
        "request_ids": [r.get("request_id") for r in ours],
        "other_caller_count": sum(1 for r in rows if caller_of(r) not in (caller, None)),
    }


# --- Langfuse --------------------------------------------------------------------------------

class LangfuseUnavailable(OSError):
    """Langfuse answered 5xx: down or starting, the same as unreachable for callers that skip."""


class Langfuse:
    """The public API with the project's key pair (`make up-obs` writes both to .env)."""

    def __init__(self, env: dict[str, str]):
        pair = f"pk-lf-{env['LANGFUSE_PROJECT_PUBLIC_SECRET']}:sk-lf-{env['LANGFUSE_PROJECT_SECRET']}"
        self.auth = "Basic " + base64.b64encode(pair.encode()).decode()

    def call(self, method: str, path: str, body: dict | None = None, headers: dict | None = None) -> dict:
        req = urllib.request.Request(
            LANGFUSE + path, method=method, data=json.dumps(body).encode() if body is not None else None,
            headers={"Authorization": self.auth, "Content-Type": "application/json", **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as e:
            msg = f"Langfuse {method} {path.split('?')[0]}: HTTP {e.code} {e.read().decode('utf-8', 'replace')[:200]}"
            raise (LangfuseUnavailable if e.code >= 500 else RuntimeError)(msg) from None
        return json.loads(raw) if raw else {}

    def pages(self, path: str) -> list[dict]:
        """Every item of a paged list endpoint (`page`/`meta.totalPages`)."""
        out, page = [], 1
        while True:
            sep = "&" if "?" in path else "?"
            doc = self.call("GET", f"{path}{sep}page={page}&limit=100")
            out += doc.get("data") or []
            if page >= int((doc.get("meta") or {}).get("totalPages") or 1):
                return out
            page += 1

    def generations(self, since: dtm.datetime, until: dtm.datetime) -> list[dict]:
        """Generations that started in [since, until]. Without `toStartTime` Langfuse 4.83 answers
        422 "narrow your request" once the project holds a compile's worth of traces (M9)."""
        out, cursor = [], None
        while True:
            path = (f"/api/public/v2/observations?type=GENERATION&limit=50&fields=core,basic,metadata"
                    f"&fromStartTime={iso(since)}&toStartTime={iso(until)}"
                    + (f"&cursor={cursor}" if cursor else ""))
            page = self.call("GET", path)
            out += page.get("data") or []
            cursor = (page.get("meta") or {}).get("cursor")
            if not cursor:
                return out

    def export_spans(self, spans: list["Span"]) -> None:
        """Traces go in over OTLP/HTTP (JSON): Langfuse 4.83 runs with
        LANGFUSE_MIGRATION_V4_WRITE_MODE=events_only, where /ingestion takes scores only."""
        doc = self.call("POST", "/api/public/otel/v1/traces", otlp_payload(spans),
                        headers={"x-langfuse-ingestion-version": "4"})
        rejected = (doc.get("partialSuccess") or {}).get("rejectedSpans")
        if rejected:
            raise RuntimeError(f"Langfuse OTLP: {rejected} span(s) rejected: {doc['partialSuccess']}")

    def ingest(self, events: list[dict]) -> None:
        """Batch ingestion (scores); Langfuse answers 207 with per-event errors, raised here."""
        batch = [{"id": str(uuid.uuid4()), "timestamp": iso(dtm.datetime.now(dtm.UTC)), **e} for e in events]
        doc = self.call("POST", "/api/public/ingestion", {"batch": batch})
        if doc.get("errors"):
            raise RuntimeError(f"Langfuse ingestion: {json.dumps(doc['errors'])[:300]}")

    def score_configs(self) -> dict[str, dict]:
        return {c["name"]: c for c in self.pages("/api/public/score-configs")}

    def queue_id(self, name: str = QUEUE) -> str:
        for q in self.pages("/api/public/annotation-queues"):
            if q.get("name") == name:
                return q["id"]
        raise RuntimeError(f"annotation queue {name!r} is missing: run make up-obs (infra/langfuse/bootstrap.py)")

    def enqueue(self, queue_id: str, trace_id: str) -> dict:
        return self.call("POST", f"/api/public/annotation-queues/{queue_id}/items",
                         {"objectId": trace_id, "objectType": "TRACE"})

    def queue_items(self, queue_id: str) -> list[dict]:
        return self.pages(f"/api/public/annotation-queues/{queue_id}/items")


@dataclasses.dataclass
class Span:
    """One OTLP span in Langfuse's terms: a root span is the trace, `attrs` use Langfuse's
    `langfuse.*` attribute names (dicts and lists are sent as JSON strings)."""
    trace_id: str                       # 32 hex characters, also the Langfuse trace id
    name: str
    start: dtm.datetime
    end: dtm.datetime
    attrs: dict
    parent_id: str | None = None
    span_id: str = dataclasses.field(default_factory=lambda: uuid.uuid4().hex[:16])


def new_trace_id() -> str:
    return uuid.uuid4().hex


def _otlp_value(v) -> dict:
    if isinstance(v, bool):
        return {"boolValue": v}
    if isinstance(v, int):
        return {"intValue": str(v)}
    if isinstance(v, float):
        return {"doubleValue": v}
    if isinstance(v, (list, tuple)) and all(isinstance(x, str) for x in v):
        return {"arrayValue": {"values": [{"stringValue": x} for x in v]}}
    if isinstance(v, (dict, list, tuple)):
        return {"stringValue": json.dumps(v, default=str)}
    return {"stringValue": str(v)}


def otlp_payload(spans: list[Span]) -> dict:
    def nano(t: dtm.datetime) -> str:
        return str(int(t.timestamp() * 1_000_000_000))
    out = []
    for s in spans:
        span = {"traceId": s.trace_id, "spanId": s.span_id, "name": s.name, "kind": 1,
                "startTimeUnixNano": nano(s.start), "endTimeUnixNano": nano(s.end),
                "attributes": [{"key": k, "value": _otlp_value(v)} for k, v in s.attrs.items() if v is not None]}
        if s.parent_id:
            span["parentSpanId"] = s.parent_id
        out.append(span)
    return {"resourceSpans": [{
        "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "wh-llm"}}]},
        "scopeSpans": [{"scope": {"name": "wh-llm"}, "spans": out}]}]}


def generation_key_alias(gen: dict) -> str | None:
    return (gen.get("metadata") or {}).get("attributes.litellm.key_alias")
