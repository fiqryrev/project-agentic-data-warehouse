"""quality_gate and run_recorder (DAG tasks 4 and 9) against a small build file."""
import json

import duckdb
import pytest

from publish import quality_gate, run_recorder
from publish.artifacts import failed_nodes, dbt_test_counts

DS = "2026-01-02"


def results(*statuses):
    """dbt run_results with one model and one test per status."""
    rows = [{"unique_id": "model.warehouse.fact__sales__orders", "status": "success"}]
    rows += [{"unique_id": f"test.warehouse.t{i}", "status": s} for i, s in enumerate(statuses)]
    return {"metadata": {"invocation_id": "inv-1"}, "results": rows}


@pytest.fixture
def build(tmp_path):
    """A build file with a lake day, a warehouse and a mart table, and the day's artifacts folder."""
    db = tmp_path / "dwh.duckdb"
    con = duckdb.connect(str(db))
    con.execute("create schema lake; create schema staging; create schema warehouse; create schema mart")
    con.execute(f"create table lake.shop__orders as select 1 as order_id, date '{DS}' as _dt")
    con.execute("create table warehouse.fact__sales__orders as select 1 as order_id")
    con.execute("create table warehouse.fact__sales__refunds (refund_id integer)")
    con.execute("create table mart.rpt__sales__orders__daily as select 1 as order_count")
    con.close()
    art = tmp_path / "artifacts"
    (art / DS).mkdir(parents=True)
    return db, art


def write_results(art, doc):
    (art / DS / "run_results.json").write_text(json.dumps(doc))


def gate(db, art, run_id="run-1"):
    code = quality_gate.main(["--ds", DS, "--db", str(db), "--run-id", run_id, "--artifacts", str(art)])
    return code, json.loads((art / DS / "quality_gate.json").read_text())


def test_counts_cover_tests_only():
    assert dbt_test_counts(results("pass", "warn", "fail", "error", "skipped")) == {"pass": 1, "warn": 1, "fail": 3}
    assert failed_nodes(results("pass", "warn")) == []


def test_gate_passes_with_warnings_and_an_empty_warehouse_table(build):
    db, art = build
    write_results(art, results("pass", "warn"))
    code, verdict = gate(db, art)
    assert code == 0 and verdict["status"] == "passed"
    assert verdict["empty_warehouse_tables"] == ["warehouse.fact__sales__refunds"]
    assert verdict["lake_day_rows"] == 1 and verdict["run_id"] == "run-1"


@pytest.mark.parametrize("status", ["fail", "error", "skipped"])
def test_gate_fails_on_a_dbt_node_that_did_not_pass(build, status):
    db, art = build
    write_results(art, results("pass", status))
    code, verdict = gate(db, art)
    assert code == 1 and "did not pass" in verdict["problems"][0]


def test_gate_fails_without_run_results(build):
    db, art = build
    code, verdict = gate(db, art)
    assert code == 1 and verdict["problems"] == ["no dbt run_results for the day"]


def test_gate_fails_when_the_day_did_not_land(build):
    db, art = build
    write_results(art, results("pass"))
    con = duckdb.connect(str(db))
    con.execute("delete from lake.shop__orders")
    con.close()
    code, verdict = gate(db, art)
    assert code == 1 and f"the lake has no row for {DS}" in verdict["problems"]


def test_gate_fails_on_an_empty_mart(build):
    db, art = build
    write_results(art, results("pass"))
    con = duckdb.connect(str(db))
    con.execute("delete from mart.rpt__sales__orders__daily")
    con.close()
    code, verdict = gate(db, art)
    assert code == 1 and "empty mart tables: mart.rpt__sales__orders__daily" in verdict["problems"]


def run_log(db):
    con = duckdb.connect(str(db), read_only=True)
    try:
        return con.execute("select run_date::varchar, run_status, dbt_invocation_id, test_pass_count, "
                           "test_warn_count, lake_row_count, mart_row_count, git_commit_id "
                           "from ops.run_log").fetchall()
    finally:
        con.close()


def test_record_writes_one_row_per_day_and_replaces_it(build, monkeypatch):
    db, art = build
    monkeypatch.setenv("GIT_SHA", "abc123")
    write_results(art, results("pass", "warn"))
    gate(db, art, "run-1")
    assert run_recorder.main(["--ds", DS, "--db", str(db), "--run-id", "run-1", "--artifacts", str(art)]) == 0
    assert run_recorder.main(["--ds", DS, "--db", str(db), "--run-id", "run-1", "--artifacts", str(art)]) == 0
    assert run_log(db) == [(DS, "passed", "inv-1", 1, 1, 1, 1, "abc123")]


def test_record_marks_a_failed_gate_and_exits_1(build):
    db, art = build
    write_results(art, results("fail"))
    gate(db, art, "run-1")
    assert run_recorder.main(["--ds", DS, "--db", str(db), "--run-id", "run-1", "--artifacts", str(art)]) == 1
    assert run_log(db)[0][1] == "failed"


def test_record_ignores_a_verdict_from_another_run(build):
    db, art = build
    write_results(art, results("pass"))
    gate(db, art, "run-old")
    row = run_recorder.record(db, DS, "run-new", art)
    assert row["run_status"] == "failed"
    assert row["run_problem_description"] == "the quality gate did not run in this run"
