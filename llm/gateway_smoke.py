"""llm-smoke: the gateway records, traces and limits model calls (M8 done-when).

    make llm-smoke            # with `make up-obs` running

1. A call through the gateway with the `agent-dev` key, tagged `job:smoke`, succeeds.
2. The same call appears in Langfuse as a generation with tokens, cost and the tags
   `job:smoke` and `caller:agent-dev` (matched on the provider's response id).
3. A caller over budget is refused: a temporary key with a tiny budget makes one call that
   spends past it, the next call gets a budget error, and the key is deleted.

Each call is one short completion on `openai/adw-or-chat` (well under a cent in total). Reads
keys from .env and prints none of them. Exit 1 if any step fails.
"""
from __future__ import annotations

import base64
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

GATEWAY = "http://127.0.0.1:4000"
LANGFUSE = "http://127.0.0.1:3001"
MODEL = "openai/adw-or-chat"
PROMPT = "Reply with the single word: pong"
TINY_BUDGET_USD = 0.000001


def read_env(path: Path = Path(".env")) -> dict[str, str]:
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines() if path.exists() else []:
        if "=" in line and not line.lstrip().startswith("#"):
            key, _, value = line.partition("=")
            out[key.strip()] = value.strip()
    return out


def http(method: str, url: str, headers: dict, body: dict | None = None,
         timeout: int = 120) -> tuple[int, dict, dict]:
    req = urllib.request.Request(url, method=method, headers={"Content-Type": "application/json", **headers},
                                 data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, dict(resp.headers), json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, dict(e.headers), json.loads(raw or b"{}")
        except ValueError:
            return e.code, dict(e.headers), {"raw": raw[:300].decode(errors="replace")}


def chat(key: str, job: str = "smoke") -> tuple[int, dict, dict]:
    body = {"model": MODEL, "messages": [{"role": "user", "content": PROMPT}],
            "max_tokens": 400, "metadata": {"tags": [f"job:{job}"]}}
    return http("POST", f"{GATEWAY}/v1/chat/completions", {"Authorization": f"Bearer {key}"}, body)


def find_generation(observations: list[dict], response_id: str) -> dict | None:
    for o in observations:
        meta = o.get("metadata") or {}
        if o.get("type") == "GENERATION" and meta.get("attributes.llm.response.id") == response_id:
            return o
    return None


def generation_facts(o: dict) -> dict:
    meta = o.get("metadata") or {}
    cost = o.get("totalCost") or (o.get("costDetails") or {}).get("total") \
        or meta.get("attributes.llm.cost.total") or 0
    return {"input_tokens": o.get("inputUsage") or 0, "output_tokens": o.get("outputUsage") or 0,
            "total_tokens": o.get("totalUsage") or 0, "cost_usd": float(cost),
            "tags": list(meta.get("attributes.langfuse.trace.tags") or []),
            "caller": meta.get("attributes.litellm.key_alias"), "model": o.get("model")}


def is_budget_refusal(status: int, body: dict) -> bool:
    """LiteLLM 1.110 refuses with HTTP 422 and error type `budget_exceeded` (seen in M8)."""
    error = body.get("error") or {}
    return 400 <= status < 500 and (error.get("type") == "budget_exceeded"
                                    or "budget has been exceeded" in str(error.get("message", "")).lower())


def budget_numbers(body: dict) -> str:
    """'Current cost: ..., Max budget: ...' from the refusal, without the key it names."""
    message = str((body.get("error") or {}).get("message", ""))
    return message[message.find("Current cost"):] if "Current cost" in message else message[:0]


def step_call_and_trace(env: dict) -> bool:
    status, headers, out = chat(env["GATEWAY_KEY_AGENT_DEV"])
    if status != 200:
        print(f"[llm-smoke] FAIL call: HTTP {status} {out}")
        return False
    usage = out.get("usage") or {}
    print(f"[llm-smoke] call ok: {MODEL}, {usage.get('prompt_tokens')} in / "
          f"{usage.get('completion_tokens')} out tokens, "
          f"${float(headers.get('x-litellm-response-cost', 0)):.8f} (gateway)")
    pk, sk = f"pk-lf-{env['LANGFUSE_PROJECT_PUBLIC_SECRET']}", f"sk-lf-{env['LANGFUSE_PROJECT_SECRET']}"
    auth = {"Authorization": "Basic " + base64.b64encode(f"{pk}:{sk}".encode()).decode()}
    url = f"{LANGFUSE}/api/public/v2/observations?type=GENERATION&limit=50&fields=core,basic,usage,metadata,model"
    for _ in range(24):                       # Langfuse ingests asynchronously; up to 2 minutes
        time.sleep(5)
        status, _, page = http("GET", url, auth, timeout=30)
        gen = find_generation(page.get("data") or [], out.get("id", "")) if status == 200 else None
        if gen:
            f = generation_facts(gen)
            ok = (f["total_tokens"] > 0 and f["cost_usd"] > 0
                  and {"job:smoke", "caller:agent-dev"} <= set(f["tags"]))
            print(f"[llm-smoke] {'trace ok' if ok else 'FAIL trace'}: Langfuse generation {gen['id']}, "
                  f"{f['input_tokens']} in / {f['output_tokens']} out tokens, ${f['cost_usd']:.8f}, "
                  f"caller {f['caller']}, tags {[t for t in f['tags'] if ':' in t and ' ' not in t]}")
            return ok
    print(f"[llm-smoke] FAIL trace: no Langfuse generation for response {out.get('id')} after 2 minutes")
    return False


def step_over_budget(env: dict) -> bool:
    master = {"Authorization": f"Bearer sk-{env['LITELLM_MASTER_SECRET']}"}
    status, _, made = http("POST", f"{GATEWAY}/key/generate", master, {
        "key_alias": f"smoke-over-budget-{int(time.time())}", "max_budget": TINY_BUDGET_USD,
        "models": [MODEL], "metadata": {"tags": ["caller:smoke-over-budget"]}})
    if status != 200 or not made.get("key"):
        print(f"[llm-smoke] FAIL budget: could not create the temporary key ({status})")
        return False
    key = made["key"]
    try:
        first, _, _ = chat(key)
        if first != 200:
            print(f"[llm-smoke] FAIL budget: the first call should pass and spend the budget, got {first}")
            return False
        for attempt in range(3):              # spend is recorded right after the call returns
            time.sleep(3)
            status, _, out = chat(key)
            if is_budget_refusal(status, out):
                print(f"[llm-smoke] budget ok: refused after spending past ${TINY_BUDGET_USD} "
                      f"(HTTP {status} {(out.get('error') or {}).get('type')}; {budget_numbers(out)})")
                return True
        print(f"[llm-smoke] FAIL budget: call {attempt + 2} still answered with HTTP {status}")
        return False
    finally:
        http("POST", f"{GATEWAY}/key/delete", master, {"keys": [key]})


def main() -> int:
    env = read_env()
    missing = [k for k in ("GATEWAY_KEY_AGENT_DEV", "LITELLM_MASTER_SECRET",
                           "LANGFUSE_PROJECT_PUBLIC_SECRET", "LANGFUSE_PROJECT_SECRET") if not env.get(k)]
    if missing:
        print(f"[llm-smoke] missing in .env: {', '.join(missing)}; run make up-obs")
        return 1
    results = [step_call_and_trace(env), step_over_budget(env)]
    print(f"[llm-smoke] {'PASS' if all(results) else 'FAIL'}")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
