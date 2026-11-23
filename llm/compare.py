"""compare-providers: the golden set once per candidate provider, before any swap (PLAN 8.6).

    make compare-providers ALIASES=nvidia,openrouter

For each candidate (a pair of gateway aliases for Auto Ontology's reasoning and non-reasoning
roles, CANDIDATES below):

1. Restart only the `auto-ontology` backend with AO_REASONING_MODEL / AO_NON_REASONING_MODEL set
   to the pair (embeddings stay `adw-embed`: changing them forces a full re-ingest). The
   ingestion service and the catalog are untouched, so no compile runs.
2. Ask every golden question, one at a time, and score it against the reference SQL on the same
   snapshot (llm/golden.py).
3. Write each answer as a trace in Langfuse experiment `<run>-<candidate>` on dataset `golden`
   (items synced from evals/golden/), session `compare:<run>:<candidate>`, with its golden scores.

Auto Ontology is restored to the default pair afterwards, also after an error. The report
docs/runs/compare-<run>.md holds accuracy, cost per correct answer, p95 latency per candidate,
and the questions whose verdict changed; that table goes into the pull request that proposes a
swap. The comparison mart (`rpt__ops__provider_comparison__snapshot`) fills after the next
task 8. Answers here are not queued for review: they are an experiment, not the served chat.
"""
from __future__ import annotations

import argparse
import datetime as dtm
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

from llm import ask as ak
from llm import golden as gd
from llm.observe import Langfuse, read_env, spend_logs

CANDIDATES = {
    "nvidia": ("openai/adw-reasoning", "openai/adw-non-reasoning"),
    "openrouter": ("openai/adw-or-chat", "openai/adw-or-non-reasoning"),
}
DEFAULT = "nvidia"
DATASET = "golden"
REPORTS = Path("docs/runs")
COMPOSE = ["docker", "compose", "-f", "infra/compose.yml", "--env-file", ".env", "--profile", "ontology"]
CORRECT = ("exact_match", "within_tolerance")


def restart_backend(pair: tuple[str, str], timeout_s: int = 300) -> None:
    """Recreate only the backend with the candidate pair, then wait until a chat session works."""
    env = {**os.environ, "AO_REASONING_MODEL": pair[0], "AO_NON_REASONING_MODEL": pair[1]}
    subprocess.run([*COMPOSE, "up", "-d", "--no-deps", "--force-recreate", "--wait", "auto-ontology"],
                   check=True, env=env, capture_output=True, text=True)
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            s = ak.sign_in(read_env())
            if s.call("GET", "/api/semantic-compilation/status")[0] == 200:
                return
        except (OSError, ak.AskError):
            pass
        if time.monotonic() > deadline:
            raise RuntimeError("Auto Ontology did not come back after the restart")
        time.sleep(5)


def running_pair() -> tuple[str, str]:
    """The alias pair the running backend uses (read from the container's environment)."""
    out = subprocess.run(["docker", "inspect", "wh-auto-ontology-1", "--format", "{{json .Config.Env}}"],
                         check=True, capture_output=True, text=True).stdout
    env = dict(e.split("=", 1) for e in __import__("json").loads(out))
    return env.get("REASONING_MODEL", ""), env.get("NON_REASONING_MODEL", "")


def sync_dataset(lf: Langfuse, questions: list[gd.Question]) -> tuple[str, dict[str, str]]:
    """Dataset `golden` with one item per golden question (item id `golden-<id>`, upserted)."""
    try:
        ds = lf.call("GET", f"/api/public/v2/datasets/{DATASET}")
    except RuntimeError:
        ds = lf.call("POST", "/api/public/v2/datasets", {
            "name": DATASET, "description": "Golden questions with reference SQL (evals/golden/)."})
    items = {}
    for q in questions:
        item = lf.call("POST", "/api/public/dataset-items", {
            "datasetName": DATASET, "id": f"golden-{q.id}", "input": {"question": q.question},
            "expectedOutput": {"reference_sql": q.reference_sql}, "metadata": {"kind": q.kind, "source": q.source}})
        items[q.id] = item.get("id", f"golden-{q.id}")
    return ds["id"], items


def experiment_attrs(run: str, cand: str, pair: tuple[str, str], dataset_id: str, item_id: str,
                     r: gd.Result, root_id: str) -> dict:
    return {"langfuse.experiment.id": f"{run}-{cand}", "langfuse.experiment.name": f"{run}-{cand}",
            "langfuse.experiment.description": f"golden set with Auto Ontology on {pair[0]} / {pair[1]}",
            "langfuse.experiment.metadata": {"candidate": cand, "reasoning_model": pair[0],
                                             "non_reasoning_model": pair[1]},
            "langfuse.experiment.dataset.id": dataset_id, "langfuse.experiment.item.id": item_id,
            "langfuse.experiment.item.expected_output": {"rows": r.expected},
            "langfuse.experiment.item.root_observation_id": root_id}


def p95(values: list[float]) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    return statistics.quantiles(values, n=20, method="inclusive")[18]


def summarise(results: list[gd.Result], latencies: list[float]) -> dict:
    correct = sum(1 for r in results if r.verdict in CORRECT)
    cost = sum(r.answer.calls.get("cost_usd") or 0 for r in results)
    return {"asked": len(results), "correct": correct,
            **{v: sum(1 for r in results if r.verdict == v) for v in gd.VERDICTS},
            "accuracy_pct": round(100 * correct / len(results), 1) if results else None,
            "cost_usd": round(cost, 6), "cost_per_correct_usd": round(cost / correct, 6) if correct else None,
            "p95_latency_ms": round(p95(latencies)) if latencies else None,
            "call_count": sum(r.answer.calls.get("call_count") or 0 for r in results)}


def report(run: str, day: str | None, rows: dict[str, dict], verdicts: dict[str, dict[str, str]],
           pairs: dict[str, tuple[str, str]]) -> str:
    cands = list(rows)
    head = ("| Candidate | Aliases | Asked | Correct | Wrong | Refused | Accuracy | Cost | Cost per correct "
            "| p95 latency |\n"
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |\n")
    body = "".join(
        f"| {c} | `{pairs[c][0]}`, `{pairs[c][1]}` | {s['asked']} | {s['correct']} | {s['wrong']} | {s['refused']} | "
        f"{s['accuracy_pct']}% | ${s['cost_usd']:.4f} | "
        + (f"${s['cost_per_correct_usd']:.4f}" if s['cost_per_correct_usd'] is not None else "n/a")
        + f" | {s['p95_latency_ms']} ms |\n" for c, s in rows.items())
    qids = sorted({q for v in verdicts.values() for q in v})
    changed = [q for q in qids if len({verdicts[c].get(q) for c in cands}) > 1]
    vt = ("| Question | " + " | ".join(cands) + " |\n| --- |" + " --- |" * len(cands) + "\n"
          + "".join(f"| {q} | " + " | ".join(verdicts[c].get(q, "-") for c in cands) + " |\n" for q in changed))
    return f"""# Provider comparison {run}

`make compare-providers` (llm/compare.py, PLAN 8.6) on the snapshot ending {day}: the golden set
asked once per candidate, Auto Ontology's reasoning and non-reasoning roles on the candidate's
aliases, embeddings on `adw-embed`. Each candidate is Langfuse experiment `{run}-<candidate>` on
dataset `{DATASET}`.

{head}{body}
Accuracy counts `exact_match` and `within_tolerance`. Cost is the gateway's list price of the
`auto-ontology` calls linked to each answer (caller key and time window); NVIDIA prices are an
estimate at the OpenRouter list price of the same model (M9). p95 latency is over the candidate's
chat calls in the run's window, from the gateway's spend log.

## Questions whose verdict changed

{vt if changed else 'None: every question got the same verdict from every candidate.'}

One run per candidate: the chat refuses a different set of questions on every run (M10), so a
single difference is weak evidence; repeat before proposing a swap on it.
"""


def chat_latencies(env: dict, pair: tuple[str, str], since: dtm.datetime, until: dtm.datetime) -> list[float]:
    rows = spend_logs(f"sk-{env['LITELLM_MASTER_SECRET']}", since, until)
    return [float(r["request_duration_ms"]) for r in rows
            if r.get("model_group") in pair and r.get("request_duration_ms") is not None]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--aliases", default="nvidia,openrouter", help=f"candidates, from {', '.join(CANDIDATES)}")
    ap.add_argument("--snapshot", type=Path, default=ak.SNAPSHOT)
    args = ap.parse_args(argv)
    cands = [c.strip() for c in args.aliases.split(",") if c.strip()]
    unknown = [c for c in cands if c not in CANDIDATES]
    if unknown or not cands:
        raise SystemExit(f"[compare] unknown candidate(s) {unknown}; known: {', '.join(CANDIDATES)}")
    env = read_env()
    lf = Langfuse(env)
    configs = lf.score_configs()
    run = "compare-" + dtm.datetime.now(dtm.UTC).strftime("%Y%m%dT%H%M")
    questions = gd.load_questions(gd.GOLDEN_DIR)
    dataset_id, items = sync_dataset(lf, questions)
    snap = ak.snapshot_hash(args.snapshot)
    rows, verdicts, day = {}, {}, None
    try:
        for cand in cands:
            pair = CANDIDATES[cand]
            print(f"[compare] {cand}: restarting Auto Ontology on {pair[0]} / {pair[1]}")
            restart_backend(pair)
            if running_pair() != pair:
                raise RuntimeError(f"the backend runs {running_pair()}, not {pair}")
            session = ak.sign_in(env)
            day, results = gd.ask_and_score(session, env, lf, args.snapshot, [gd.GOLDEN_DIR], label=f"[compare] {cand}")
            since = min(r.answer.window[0] for r in results)
            until = max(r.answer.window[1] for r in results)
            sid = f"compare:{run}:{cand}"
            spans, scores = [], []
            for r in results:
                extra = {**gd.answer_extra(r), "comparison_run": run, "candidate": cand,
                         "reasoning_model": pair[0], "non_reasoning_model": pair[1]}
                root, chat = ak.answer_spans(r.answer, session_id=sid, snapshot=snap, extra=extra,
                                             tags=["job:compare", f"candidate:{cand}", f"golden:{r.q.id}",
                                                   f"verdict:{r.verdict}"])
                root.attrs.update(experiment_attrs(run, cand, pair, dataset_id, items[r.q.id], r, root.span_id))
                spans += [root, chat]
                scores += gd.score_events(r, configs)
            lf.export_spans(spans)
            if scores:
                lf.ingest(scores)
            rows[cand] = summarise(results, chat_latencies(env, pair, since, until))
            verdicts[cand] = {r.q.id: r.verdict for r in results}
            s = rows[cand]
            print(f"[compare] {cand}: {s['correct']} of {s['asked']} correct ({s['accuracy_pct']}%), "
                  f"{s['wrong']} wrong, {s['refused']} refused; ${s['cost_usd']:.4f}; p95 {s['p95_latency_ms']} ms")
    finally:
        print(f"[compare] restoring Auto Ontology on {CANDIDATES[DEFAULT][0]} / {CANDIDATES[DEFAULT][1]}")
        restart_backend(CANDIDATES[DEFAULT])
    REPORTS.mkdir(parents=True, exist_ok=True)
    path = REPORTS / f"{run}.md"
    path.write_text(report(run, day, rows, verdicts, {c: CANDIDATES[c] for c in rows}), encoding="utf-8")
    print(f"[compare] report: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
