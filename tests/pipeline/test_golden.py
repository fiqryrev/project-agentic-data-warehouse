"""Golden runner and ask client: scoring, SQL re-run, call linking and trace events, without a network."""
import datetime as dtm
from pathlib import Path

import duckdb
import pytest

from llm import ask as ak
from llm import golden as g
from llm.observe import calls_summary, otlp_payload

REPO = Path(__file__).resolve().parents[2]
SCALAR = g.Question("g-0001", "q", "select 1", tolerance_pct=0.5)
ROWS = g.Question("g-0006", "q", "select 1", kind="rows", key="channel_name", tolerance_pct=0.5)


def test_answer_rows_parse_the_json_string_auto_ontology_sends():
    assert ak.answer_rows(['[{"net_revenue_idr":718490209.0}]']) == [{"net_revenue_idr": 718490209.0}]
    assert ak.answer_rows([{"a": 1}, '[{"b": 2}]']) == [{"a": 1}, {"b": 2}]
    assert ak.answer_rows(None) is None and ak.answer_rows("not json") is None


@pytest.mark.parametrize("rows, verdict", [
    ([{"net_revenue_idr": 718490209.0}], "exact_match"),
    ([{"revenue_date": "2026-01-05", "net_revenue_idr": 718490209}], "exact_match"),
    ([{"net_revenue_idr": 718000000}], "within_tolerance"),
    ([{"net_revenue_idr": 700000000}], "wrong"),
    ([], "refused"),
    (None, "refused"),
    ([{"note": "no data"}], "refused"),
    ([{"v": 718490209}] * 25, "wrong"),
])
def test_scalar_verdicts(rows, verdict):
    assert g.score_answer(SCALAR, ["net_revenue_idr"], [(718490209,)], rows)[0] == verdict


def test_exact_only_when_tolerance_is_zero():
    q = g.Question("g-0002", "q", "select 1", tolerance_pct=0)
    assert g.score_answer(q, ["n"], [(665,)], [{"n": 665}])[0] == "exact_match"
    assert g.score_answer(q, ["n"], [(665,)], [{"n": 664}])[0] == "wrong"


def test_rows_verdicts():
    ref_cols = ["channel_name", "spend_idr"]
    ref = [("email", 2020000), ("google", 1766000), ("tiktok", 2077000)]
    ok = [{"channel_name": "Email", "spend_idr": 2020000}, {"channel_name": "google", "spend_idr": 1766000},
          {"channel_name": "tiktok", "spend_idr": 2077000.0}]
    assert g.score_answer(ROWS, ref_cols, ref, ok)[0] == "exact_match"
    assert g.score_answer(ROWS, ref_cols, ref, ok[:2])[0] == "wrong"
    off = ok[:2] + [{"channel_name": "tiktok", "spend_idr": 2070000}]
    assert g.score_answer(ROWS, ref_cols, ref, off)[0] == "within_tolerance"


@pytest.fixture()
def snapshot(tmp_path):
    path = tmp_path / "analytics.duckdb"
    con = duckdb.connect(str(path))
    con.execute("create schema data_mart_layer")
    con.execute("create table data_mart_layer.rpt__finance__revenue__daily as "
                "select date '2026-01-05' as revenue_date, 718490209::hugeint as net_revenue_idr")
    con.close()
    return path


def test_sql_consistent_reruns_the_answer_sql_read_only(snapshot, tmp_path):
    con = g.connect(snapshot)
    sql = "SELECT net_revenue_idr FROM data_mart_layer.rpt__finance__revenue__daily WHERE revenue_date = '2026-01-05'"
    assert g.sql_consistent(con, sql, [{"net_revenue_idr": 718490209.0}])[0] is True
    assert g.sql_consistent(con, sql, [{"net_revenue_idr": 1.0}])[0] is False
    assert g.sql_consistent(con, None, None)[0] is None
    assert g.sql_consistent(con, "drop table data_mart_layer.rpt__finance__revenue__daily", [])[0] is False
    out = tmp_path / "leak.csv"
    assert g.sql_consistent(con, f"copy (select 1) to '{out}'", [])[0] is False
    assert not out.exists()
    assert g.snapshot_day(con) == "2026-01-05"
    con.close()


def test_load_questions_reads_the_repo_set():
    qs = g.load_questions(REPO / "evals" / "golden")
    assert len(qs) >= 6 and len({q.id for q in qs}) == len(qs)
    assert all(q.kind in ("scalar", "rows") and q.needs_day for q in qs)


def test_calls_are_linked_by_caller_and_window():
    rows = [{"metadata": {"user_api_key_alias": "auto-ontology"}, "spend": 0.001, "prompt_tokens": 10,
             "completion_tokens": 5, "model_group": "openai/adw-reasoning", "request_id": "a"},
            {"metadata": '{"user_api_key_alias": "agent-dev"}', "spend": 9, "request_id": "b"},
            {"metadata": {}, "spend": 0, "request_id": "c"}]
    s = calls_summary(rows, "auto-ontology")
    assert (s["call_count"], s["cost_usd"], s["prompt_tokens"], s["other_caller_count"]) == (1, 0.001, 10, 1)


def test_queue_rule_and_trace_events():
    t0 = dtm.datetime(2026, 11, 22, 8, 0, tzinfo=dtm.UTC)
    a = ak.Answer("q", t0, t0 + dtm.timedelta(seconds=30), text="x", sql="select 1", rows=[{"n": 1}])
    r = g.Result(SCALAR, a, "within_tolerance", "", False, "", [[1]])
    assert r.queued                                    # inconsistent SQL goes to a person too
    assert not g.Result(SCALAR, a, "exact_match", "", True, "", [[1]]).queued
    assert g.Result(SCALAR, a, "refused", "", None, "", [[1]]).queued
    root, chat = ak.answer_spans(a, session_id="golden:d:r", tags=["job:golden"], snapshot="h")
    assert len(root.trace_id) == 32 and chat.parent_id == root.span_id and chat.trace_id == root.trace_id
    assert root.attrs["langfuse.trace.name"] == "ask" and root.attrs["langfuse.session.id"] == "golden:d:r"
    assert root.attrs["langfuse.trace.metadata.linked_calls"]["method"] == "caller_key+time_window"
    span = otlp_payload([root, chat])["resourceSpans"][0]["scopeSpans"][0]["spans"]
    attrs = {x["key"]: x["value"] for x in span[0]["attributes"]}
    assert attrs["langfuse.trace.tags"] == {"arrayValue": {"values": [{"stringValue": "job:golden"}]}}
    assert '"caller_key+time_window"' in attrs["langfuse.trace.metadata.linked_calls"]["stringValue"]
    assert "parentSpanId" not in span[0] and span[1]["parentSpanId"] == root.span_id
    configs = {"golden_verdict": {"id": "c1"}, "sql_consistent": {"id": "c2"}}
    scores = g.score_events(r, configs)
    assert [s["body"]["name"] for s in scores] == ["golden_verdict", "sql_consistent"]
    assert scores[1]["body"]["value"] == 0


def test_disabled_run_is_skipped(tmp_path, monkeypatch):
    monkeypatch.setattr(g, "ARTIFACTS", tmp_path)
    assert g.main(["--ds", "2026-01-08", "--enabled", "false"]) == g.SKIP
    assert '"skipped"' in (tmp_path / "2026-01-08" / "golden.json").read_text()
