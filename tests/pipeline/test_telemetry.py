"""Task 8 land_llm_telemetry: row mapping, landing and loading by real date, without a network."""
import datetime as dtm

import duckdb

from llm import telemetry as t
from loader.load import load_day

DAY = dtm.date(2026, 11, 22)
SPEND = {"request_id": "r1", "call_type": "acompletion", "metadata": {"user_api_key_alias": "auto-ontology"},
         "model_group": "openai/adw-reasoning", "model": "m", "custom_llm_provider": "nvidia_nim",
         "status": "success", "request_tags": ["job:golden", "User-Agent: x"],
         "startTime": "2026-11-22T08:00:00Z", "endTime": "2026-11-22T08:00:02Z", "request_duration_ms": 2000,
         "prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15, "spend": 0.001, "cache_hit": "None"}
TRACE = {"id": "a" * 32, "sessionId": "golden:2026-01-10:r", "tags": ["job:golden"], "timestamp": "2026-11-22T08:00:00Z",
         "input": {"question": "q"}, "output": {"answer": "x", "sql": "select 1", "row_count": 1},
         "metadata": {"golden_id": "g-0001", "golden_verdict": "wrong", "sql_consistent": True,
                      "linked_calls": {"method": "caller_key+time_window", "cost_usd": 0.01, "call_count": 3}}}
SCORE = {"id": "s1", "traceId": "a" * 32, "name": "verdict", "dataType": "CATEGORICAL", "value": 2,
         "stringValue": "wrong_definition", "source": "ANNOTATION", "timestamp": "2026-11-22T09:00:00Z"}


def test_rows_map_each_source():
    s = t.spend_row(SPEND)
    assert (s["caller_alias"], s["spend_usd"], s["duration_ms"], s["provider"]) == ("auto-ontology", 0.001, 2000, "nvidia_nim")
    assert '"job:golden"' in s["job_tags"] and s["started_at"] == dtm.datetime(2026, 11, 22, 8)
    a = t.answer_row(TRACE)
    assert (a["golden_verdict"], a["linked_call_count"], a["question"], a["sql_consistent"]) == ("wrong", 3, "q", True)
    sc = t.score_row(SCORE)
    assert (sc["name"], sc["string_value"], sc["source"]) == ("verdict", "wrong_definition", "ANNOTATION")


def test_landing_loads_with_audit_columns_and_replaces_a_day(tmp_path):
    db = tmp_path / "dwh.duckdb"
    con = duckdb.connect(str(db))
    assert len(t.ensure_tables(con)) == 4 and t.ensure_tables(con) == []
    rows = {"gateway.spend_logs": [t.spend_row(SPEND)], "langfuse.answers": [t.answer_row(TRACE)],
            "langfuse.scores": [t.score_row(SCORE)]}
    for _ in range(2):                                    # a re-landed day replaces itself
        t.write_day(tmp_path / "landing", DAY, rows)
        counts = load_day(con, tmp_path / "landing", DAY)
    assert counts["data_lake_layer.gateway__spend_logs"] == 1 and counts["data_lake_layer.airflow__run_log"] == 0
    got = con.execute("select count(*), max(_dt), max(_batch_id) from data_lake_layer.langfuse__scores").fetchone()
    assert got[0] == 1 and got[1] == DAY and got[2].startswith("2026-11-22-")
    con.close()


def test_days_to_land_start_at_the_last_landed_day(tmp_path):
    assert t.days_to_land(tmp_path, DAY, lookback=2) == [DAY - dtm.timedelta(days=2), DAY - dtm.timedelta(days=1), DAY]
    t.write_day(tmp_path, DAY - dtm.timedelta(days=1), {})
    assert t.days_to_land(tmp_path, DAY) == [DAY - dtm.timedelta(days=1), DAY]


def test_run_log_rows_come_from_the_build_file(tmp_path):
    db = tmp_path / "b.duckdb"
    con = duckdb.connect(str(db))
    con.execute("create schema ops; create table ops.run_log (run_date date, run_status varchar, recorded_at timestamp)")
    con.execute("insert into ops.run_log values ('2026-01-10', 'failed', '2026-11-22 08:30:00'), "
                "('2026-01-09', 'passed', '2026-11-21 08:30:00')")
    con.close()
    rows = t.run_log_rows(db, *t.day_bounds(DAY))
    assert [(r["run_date"], r["run_status"], r["golden_status"]) for r in rows] == [(dtm.date(2026, 1, 10), "failed", None)]
