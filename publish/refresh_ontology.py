"""refresh_ontology (DAG task 6): make Auto Ontology serve the snapshot just published.

Both Auto Ontology services keep the old serving file open until they restart (M0, item 3), so:
1. Restart `ingestion-service` and `auto-ontology` through the socket proxy, which allows exactly
   those two restarts (infra/compose.yml, docker-proxy).
2. Wait for the ingestion service: on start it ingests the new file, then runs one semantic
   compile pass (compile is enabled by the ao-seed service). The pass is incremental: tables
   already compiled are not compiled again (M0). Wait until `/semantic/status` reports a success
   newer than the restart.
3. Write data/artifacts/<ds>/refresh.json in every outcome (passed, failed, skipped), so the run
   recorder never has to guess what a missing report means.

Exit 99 (Airflow marks the task skipped) when the ontology profile is not running, so the core
profile alone still runs and backfills days (M7).

    uv run python -m publish.refresh_ontology --ds 2026-01-07 --run-id manual
"""
from __future__ import annotations

import argparse
import datetime as dtm
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from publish.artifacts import ARTIFACTS, day_dir, write_json

SKIP = 99
PROXY = os.environ.get("DOCKER_PROXY_URL", "http://docker-proxy:2375")
INGESTION = os.environ.get("INGESTION_SERVICE_URL", "http://ingestion-service:3002")
CONTAINERS = ("wh-ingestion-service-1", "wh-auto-ontology-1")
API = "v1.41"


def request(method: str, url: str, timeout: int = 30) -> tuple[int, dict]:
    req = urllib.request.Request(url, method=method, data=b"" if method == "POST" else None)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            return resp.status, json.loads(body) if body.strip().startswith(b"{") else {}
    except urllib.error.HTTPError as e:
        return e.code, {}
    except (urllib.error.URLError, OSError):
        return 0, {}


def parse_time(value: str | None) -> dtm.datetime | None:
    if not value:
        return None
    t = dtm.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=dtm.UTC)


def compile_done(status: dict, since: dtm.datetime) -> tuple[bool, str | None]:
    """(finished, error) for a /semantic/status body, judged against the restart time."""
    if status.get("running"):
        return False, None
    failed, ok = parse_time(status.get("last_failure_at")), parse_time(status.get("last_success_at"))
    if failed and failed >= since:
        return True, f"semantic compile failed at {failed.isoformat()}"
    if ok and ok >= since:
        return True, None
    return False, None


def refresh(ds: str, run_id: str, artifacts: Path = ARTIFACTS, timeout_s: int = 3600,
            poll_s: int = 15) -> int:
    report = day_dir(ds, artifacts) / "refresh.json"
    if request("GET", f"{PROXY}/_ping", timeout=5)[0] != 200:
        write_json(report, {"ds": ds, "run_id": run_id, "status": "skipped",
                            "error": None, "reason": "the ontology profile is not running"})
        print("[refresh_ontology] the ontology profile is not running (no docker proxy); skipped")
        return SKIP
    since = dtm.datetime.now(dtm.UTC)
    for name in CONTAINERS:
        code, _ = request("POST", f"{PROXY}/{API}/containers/{name}/restart?t=20", timeout=120)
        if code != 204:
            error = f"restart {name} failed: HTTP {code}"
            write_json(report, {"ds": ds, "run_id": run_id, "restarted_at": since.isoformat(),
                                "status": "failed", "error": error})
            print(f"[refresh_ontology] {error}")
            return 1
        print(f"[refresh_ontology] restarted {name}")
    deadline = time.monotonic() + timeout_s
    error, status = "timed out waiting for the semantic compile pass", {}
    while time.monotonic() < deadline:
        time.sleep(poll_s)
        code, status = request("GET", f"{INGESTION}/semantic/status")
        if code != 200:
            continue                     # the service is still starting
        done, err = compile_done(status, since)
        if done:
            error = err
            break
    took = (dtm.datetime.now(dtm.UTC) - since).total_seconds()
    write_json(report,
               {"ds": ds, "run_id": run_id, "restarted_at": since.isoformat(), "seconds": round(took),
                "status": "failed" if error else "passed", "error": error, "semantic_status": status})
    if error:
        print(f"[refresh_ontology] {error}")
        return 1
    print(f"[refresh_ontology] {ds}: ingest and compile finished in {took:.0f}s")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ds", required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--artifacts", type=Path, default=ARTIFACTS)
    ap.add_argument("--timeout", type=int, default=3600)
    args = ap.parse_args(argv)
    return refresh(args.ds, args.run_id, args.artifacts, args.timeout)


if __name__ == "__main__":
    sys.exit(main())
