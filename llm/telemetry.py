"""land_llm_telemetry (DAG task 8): model calls, answers, scores and run records into the lake (PLAN 8.4).

    uv run python -m llm.telemetry --db data/dev/dwh.duckdb          # by hand
    uv run python -m llm.telemetry --db <file> --init-only            # empty tables (CI)

Four tables, each landed as Parquet with a manifest and loaded by the project's loader, so they
carry the same audit columns as every lake table:

    gateway.spend_logs   one row per gateway call (caller key, alias, provider, status, latency,
                         tokens, cost in USD, job tags)
    langfuse.scores      one row per Langfuse score: automatic (golden_verdict, sql_consistent)
                         and human labels from the queue (verdict, reasoning_ok, correct_*, note)
    langfuse.answers     one row per `ask` answer trace (question, answer, SQL, golden verdict,
                         linked cost)
    airflow.run_log      the rows of ops.run_log recorded that day

Partitions are real UTC dates (`_dt` = the day the call, score or record happened): the DAG's
dates are synthetic (2026-01-xx) while telemetry happens now. Each run lands from the last
landed day (which may have been partial) to today, so a rerun replaces whole days and loading
stays idempotent. Exit 99 (skipped) when the gateway or Langfuse is not reachable.
"""
from __future__ import annotations

import argparse
import datetime as dtm
import hashlib
import json
import shlex
import subprocess
import sys
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from llm.observe import Langfuse, caller_of, iso, parse_time, read_env, spend_logs
from loader.load import AUDIT_COLUMNS, SCHEMA, load_day, manifest_file, partition_file
from publish.artifacts import ARTIFACTS, day_dir, write_json

LANDING = Path("data/landing-telemetry")
SKIP = 99
LOOKBACK_DAYS = 7              # the first run lands this many days back

TS = pa.timestamp("us")
TABLES: dict[str, pa.Schema] = {
    "gateway.spend_logs": pa.schema([
        ("request_id", pa.string()), ("call_type", pa.string()), ("caller_alias", pa.string()),
        ("model_group", pa.string()), ("model", pa.string()), ("provider", pa.string()),
        ("status", pa.string()), ("job_tags", pa.string()), ("started_at", TS), ("ended_at", TS),
        ("duration_ms", pa.int64()), ("prompt_tokens", pa.int64()), ("completion_tokens", pa.int64()),
        ("total_tokens", pa.int64()), ("spend_usd", pa.float64()), ("cache_hit", pa.string()),
    ]),
    "langfuse.scores": pa.schema([
        ("score_id", pa.string()), ("trace_id", pa.string()), ("observation_id", pa.string()),
        ("name", pa.string()), ("data_type", pa.string()), ("value", pa.float64()),
        ("string_value", pa.string()), ("comment", pa.string()), ("source", pa.string()),
        ("author_user_id", pa.string()), ("config_id", pa.string()), ("queue_id", pa.string()),
        ("scored_at", TS), ("updated_at", TS),
    ]),
    "langfuse.answers": pa.schema([
        ("trace_id", pa.string()), ("session_id", pa.string()), ("tags", pa.string()),
        ("started_at", TS), ("question", pa.string()), ("answer", pa.string()), ("sql", pa.string()),
        ("row_count", pa.int64()), ("error", pa.string()), ("snapshot_hash", pa.string()),
        ("golden_id", pa.string()), ("golden_verdict", pa.string()), ("sql_consistent", pa.bool_()),
        ("linked_cost_usd", pa.float64()), ("linked_call_count", pa.int64()), ("link_method", pa.string()),
    ]),
    "airflow.run_log": pa.schema([
        ("run_date", pa.date32()), ("dag_run_id", pa.string()), ("git_commit_id", pa.string()),
        ("run_status", pa.string()), ("run_problem_description", pa.string()),
        ("lake_day_row_count", pa.int64()), ("lake_row_count", pa.int64()),
        ("warehouse_row_count", pa.int64()), ("mart_row_count", pa.int64()),
        ("test_pass_count", pa.int64()), ("test_warn_count", pa.int64()), ("test_fail_count", pa.int64()),
        ("snapshot_hash_code", pa.string()), ("ontology_refresh_status", pa.string()),
        ("golden_status", pa.string()), ("golden_question_count", pa.int64()),
        ("golden_wrong_count", pa.int64()), ("golden_refused_count", pa.int64()), ("recorded_at", TS),
    ]),
}


def _naive(value) -> dtm.datetime | None:
    return parse_time(value).astimezone(dtm.UTC).replace(tzinfo=None) if value else None


def _int(value) -> int | None:
    try:
        return None if value is None else int(value)
    except (TypeError, ValueError):
        return None


def _float(value) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _json(value) -> str | None:
    return None if value is None else json.dumps(value, default=str, sort_keys=True)


def _meta(value) -> dict:
    if isinstance(value, str):
        try:
            value = json.loads(value or "{}")
        except ValueError:
            return {}
    return value if isinstance(value, dict) else {}


# --- rows from each source -------------------------------------------------------------------

def spend_row(r: dict) -> dict:
    meta = _meta(r.get("metadata"))
    tags = r.get("request_tags")
    return {
        "request_id": r.get("request_id"), "call_type": r.get("call_type"), "caller_alias": caller_of(r),
        "model_group": r.get("model_group"), "model": r.get("model"),
        "provider": r.get("custom_llm_provider"), "status": r.get("status") or meta.get("status"),
        "job_tags": _json(tags if isinstance(tags, list) else _meta(tags) or tags),
        "started_at": _naive(r.get("startTime")), "ended_at": _naive(r.get("endTime")),
        "duration_ms": _int(r.get("request_duration_ms")),
        "prompt_tokens": _int(r.get("prompt_tokens")), "completion_tokens": _int(r.get("completion_tokens")),
        "total_tokens": _int(r.get("total_tokens")), "spend_usd": _float(r.get("spend")),
        "cache_hit": None if r.get("cache_hit") is None else str(r.get("cache_hit")),
    }


def score_row(s: dict) -> dict:
    return {
        "score_id": s.get("id"), "trace_id": s.get("traceId"), "observation_id": s.get("observationId"),
        "name": s.get("name"), "data_type": s.get("dataType"), "value": _float(s.get("value")),
        "string_value": s.get("stringValue"), "comment": s.get("comment"), "source": s.get("source"),
        "author_user_id": s.get("authorUserId"), "config_id": s.get("configId"), "queue_id": s.get("queueId"),
        "scored_at": _naive(s.get("timestamp")), "updated_at": _naive(s.get("updatedAt")),
    }


def answer_row(t: dict) -> dict:
    out, meta = _meta(t.get("output")), _meta(t.get("metadata"))
    link = _meta(meta.get("linked_calls"))
    consistent = meta.get("sql_consistent")
    return {
        "trace_id": t.get("id"), "session_id": t.get("sessionId"), "tags": _json(t.get("tags") or []),
        "started_at": _naive(t.get("timestamp")), "question": (_meta(t.get("input")) or {}).get("question"),
        "answer": out.get("answer"), "sql": out.get("sql"), "row_count": _int(out.get("row_count")),
        "error": out.get("error"), "snapshot_hash": meta.get("snapshot_hash"),
        "golden_id": meta.get("golden_id"), "golden_verdict": meta.get("golden_verdict"),
        "sql_consistent": consistent if isinstance(consistent, bool) else None,
        "linked_cost_usd": _float(link.get("cost_usd", meta.get("cost_usd"))),
        "linked_call_count": _int(link.get("call_count", meta.get("call_count"))),
        "link_method": link.get("method"),
    }


def day_bounds(day: dtm.date) -> tuple[dtm.datetime, dtm.datetime]:
    start = dtm.datetime.combine(day, dtm.time(), dtm.UTC)
    return start, start + dtm.timedelta(days=1) - dtm.timedelta(microseconds=1)


def fetch_day(day: dtm.date, env: dict, lf: Langfuse, build_db: Path | None) -> dict[str, list[dict]]:
    since, until = day_bounds(day)
    gw = [spend_row(r) for r in spend_logs(f"sk-{env['LITELLM_MASTER_SECRET']}", since, until)]
    window = f"fromTimestamp={iso(since)}&toTimestamp={iso(until)}"
    scores = [score_row(s) for s in lf.pages(f"/api/public/scores?{window}")]
    answers = [answer_row(t) for t in lf.pages(f"/api/public/traces?name=ask&{window}")]
    return {"gateway.spend_logs": gw, "langfuse.scores": scores, "langfuse.answers": answers,
            "airflow.run_log": run_log_rows(build_db, since, until)}


def run_log_rows(build_db: Path | None, since: dtm.datetime, until: dtm.datetime) -> list[dict]:
    if not build_db or not build_db.exists():
        return []
    cols = TABLES["airflow.run_log"].names
    con = duckdb.connect(str(build_db), read_only=True)
    try:
        have = {r[0] for r in con.execute("select column_name from information_schema.columns "
                                          "where table_schema = 'ops' and table_name = 'run_log'").fetchall()}
        if not have:
            return []
        select = ", ".join(c if c in have else f"null as {c}" for c in cols)
        rows = con.execute(f"select {select} from ops.run_log where recorded_at between ? and ?",
                           [since.replace(tzinfo=None), until.replace(tzinfo=None)]).fetchall()
    finally:
        con.close()
    return [dict(zip(cols, r)) for r in rows]


# --- landing and loading ---------------------------------------------------------------------

def write_day(landing: Path, day: dtm.date, rows: dict[str, list[dict]]) -> dict:
    """Parquet per table plus a manifest the loader checks (rows and SHA-256)."""
    tables = {}
    for key, schema in TABLES.items():
        source, _, table = key.partition(".")
        path = partition_file(landing, source, table, day)
        path.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(pa.Table.from_pylist(rows.get(key) or [], schema=schema), path)
        tables[key] = {"rows": len(rows.get(key) or []), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    manifest = {"date": day.isoformat(), "writer": "llm.telemetry", "tables": tables}
    mf = manifest_file(landing, day)
    mf.parent.mkdir(parents=True, exist_ok=True)
    mf.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def ensure_tables(con: duckdb.DuckDBPyConnection) -> list[str]:
    """Create the empty lake tables with their fixed columns when missing, so dbt builds on a
    file that has never landed telemetry (CI). Returns the tables created."""
    con.execute(f"create schema if not exists {SCHEMA}")
    made = []
    for key, schema in TABLES.items():
        name = key.replace(".", "__")
        if con.execute("select 1 from information_schema.tables where table_schema = ? and table_name = ?",
                       [SCHEMA, name]).fetchone():
            continue
        empty = pa.Table.from_pylist([], schema=schema)  # noqa: F841 (read by DuckDB below)
        audit = ", ".join(f"null::{typ} as {col}" for col, (typ, _) in AUDIT_COLUMNS.items())
        # `dt` as the loader's tables have it: DuckDB reads the hive folder dt=... as a column.
        con.execute(f"create table {SCHEMA}.{name} as select *, null::date as dt, {audit} from empty limit 0")
        con.execute(f"comment on table {SCHEMA}.{name} is 'Lake copy of the landing source table; append-only by _dt.'")
        made.append(f"{SCHEMA}.{name}")
    return made


def last_landed(landing: Path) -> dtm.date | None:
    days = sorted(p.name.removeprefix("dt=") for p in (landing / "_manifest").glob("dt=*"))
    return dtm.date.fromisoformat(days[-1]) if days else None


def days_to_land(landing: Path, today: dtm.date, lookback: int = LOOKBACK_DAYS) -> list[dtm.date]:
    start = last_landed(landing) or today - dtm.timedelta(days=lookback)
    start = min(start, today)
    return [start + dtm.timedelta(days=n) for n in range((today - start).days + 1)]


def report(ds: str | None, run_id: str, status: str, **extra) -> None:
    """data/artifacts/<ds>/telemetry.json for record_run, when run by the DAG."""
    if ds:
        write_json(day_dir(ds, ARTIFACTS) / "telemetry.json", {"ds": ds, "run_id": run_id, "status": status, **extra})


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", type=Path, required=True, help="the DuckDB file whose lake receives the tables")
    ap.add_argument("--landing", type=Path, default=LANDING)
    ap.add_argument("--init-only", action="store_true", help="only create the empty tables")
    ap.add_argument("--ds", help="the DAG run's date: write data/artifacts/<ds>/telemetry.json")
    ap.add_argument("--run-id", default="manual")
    ap.add_argument("--dbt", help="dbt command to run after loading (the DAG rebuilds the ops models)")
    ap.add_argument("--today", type=dtm.date.fromisoformat, default=None, help="for tests")
    args = ap.parse_args(argv)
    con = duckdb.connect(str(args.db))
    try:
        made = ensure_tables(con)
    finally:
        con.close()
    if args.init_only:
        print(f"[telemetry] {len(made)} empty table(s) created; {len(TABLES) - len(made)} already there")
        return 0
    env = read_env()
    lf = Langfuse(env)
    today = args.today or dtm.datetime.now(dtm.UTC).date()
    days = days_to_land(args.landing, today)
    try:
        fetched = {d: fetch_day(d, env, lf, args.db) for d in days}
    except OSError as e:
        report(args.ds, args.run_id, "skipped", reason=f"gateway or Langfuse not reachable: {e}")
        print(f"[telemetry] gateway or Langfuse not reachable ({e}); skipped")
        return SKIP
    rows: dict[str, int] = {}
    try:
        con = duckdb.connect(str(args.db))
        try:
            for d, day_rows in fetched.items():
                write_day(args.landing, d, day_rows)
                counts = load_day(con, args.landing, d)
                for k, v in counts.items():
                    rows[k.split(".")[-1]] = rows.get(k.split(".")[-1], 0) + v
                print(f"[telemetry] {d}: " + ", ".join(f"{k.split('.')[-1]} {v}" for k, v in sorted(counts.items())))
        finally:
            con.close()
        if args.dbt:
            done = subprocess.run(shlex.split(args.dbt), cwd="dbt")
            if done.returncode != 0:
                raise RuntimeError(f"dbt exited {done.returncode}")
    except Exception as e:                    # noqa: BLE001 (reported, then re-raised as exit 1)
        report(args.ds, args.run_id, "failed", error=str(e)[:300], days=[str(d) for d in days], rows=rows)
        print(f"[telemetry] FAIL: {e}")
        return 1
    report(args.ds, args.run_id, "passed", days=[str(d) for d in days], rows=rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
