"""quality_gate and run_recorder (DAG tasks 4 and 9) against a small build file."""
import json

import duckdb
import pytest

import datetime as dtm

from publish import quality_gate, refresh_ontology, run_recorder, snapshot
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
    con.execute("create schema data_lake_layer; create schema data_staging_layer; create schema data_warehouse_layer; create schema data_mart_layer")
    con.execute(f"create table data_lake_layer.shop__orders as select 1 as order_id, date '{DS}' as _dt")
    con.execute("create table data_warehouse_layer.fact__sales__orders as select 1 as order_id")
    con.execute("create table data_warehouse_layer.fact__sales__refunds (refund_id integer)")
    con.execute("create table data_mart_layer.rpt__sales__orders__daily as select 1 as order_count")
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
    assert verdict["empty_warehouse_tables"] == ["data_warehouse_layer.fact__sales__refunds"]
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
    con.execute("delete from data_lake_layer.shop__orders")
    con.close()
    code, verdict = gate(db, art)
    assert code == 1 and f"the lake has no row for {DS}" in verdict["problems"]


def test_gate_fails_on_an_empty_mart(build):
    db, art = build
    write_results(art, results("pass"))
    con = duckdb.connect(str(db))
    con.execute("delete from data_mart_layer.rpt__sales__orders__daily")
    con.close()
    code, verdict = gate(db, art)
    assert code == 1 and "empty mart tables: data_mart_layer.rpt__sales__orders__daily" in verdict["problems"]


def run_log(db):
    con = duckdb.connect(str(db), read_only=True)
    try:
        return con.execute("select run_date::varchar, run_status, dbt_invocation_id, test_pass_count, "
                           "test_warn_count, lake_row_count, mart_row_count, git_commit_id "
                           "from ops.run_log").fetchall()
    finally:
        con.close()


def publish(db, art, run_id="run-1"):
    return snapshot.publish(db, DS, run_id, serve=art.parent / "serve", artifacts=art)


def skipped_refresh(art, run_id="run-1"):
    (art / DS / "refresh.json").write_text(json.dumps({"run_id": run_id, "status": "skipped"}))
    telemetry(art, run_id)


def telemetry(art, run_id="run-1", status="passed"):
    (art / DS).mkdir(parents=True, exist_ok=True)
    (art / DS / "telemetry.json").write_text(json.dumps({"run_id": run_id, "status": status, "error": "boom"}))


def test_record_writes_one_row_per_day_and_replaces_it(build, monkeypatch):
    db, art = build
    monkeypatch.setenv("GIT_SHA", "abc123")
    write_results(art, results("pass", "warn"))
    gate(db, art, "run-1")
    publish(db, art)
    skipped_refresh(art)
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
    telemetry(art, "run-new")
    row = run_recorder.record(db, DS, "run-new", art)
    assert row["run_status"] == "failed"
    assert row["run_problem_description"] == "the quality gate did not run in this run"


def test_record_fails_a_day_whose_snapshot_was_not_published(build):
    db, art = build
    write_results(art, results("pass"))
    gate(db, art, "run-1")
    row = run_recorder.record(db, DS, "run-1", art)
    assert row["run_status"] == "failed"
    assert "snapshot was not published" in row["run_problem_description"]


def test_record_keeps_snapshot_hash_and_refresh_status(build):
    db, art = build
    write_results(art, results("pass"))
    gate(db, art, "run-1")
    doc = publish(db, art)
    (art / DS / "refresh.json").write_text(json.dumps({"run_id": "run-1", "status": "skipped"}))
    telemetry(art)
    row = run_recorder.record(db, DS, "run-1", art)
    assert row["run_status"] == "passed" and row["ontology_refresh_status"] == "skipped"
    assert row["snapshot_hash_code"] == doc["snapshot_hash"]
    (art / DS / "refresh.json").write_text(json.dumps({"run_id": "run-1", "status": "failed", "error": "boom"}))
    row = run_recorder.record(db, DS, "run-1", art)
    assert row["run_status"] == "failed" and "ontology refresh failed: boom" in row["run_problem_description"]


def test_record_keeps_the_golden_result_and_fails_a_wrong_answer(build):
    db, art = build
    write_results(art, results("pass"))
    gate(db, art, "run-1")
    publish(db, art)
    (art / DS / "refresh.json").write_text(json.dumps({"run_id": "run-1", "status": "passed"}))
    telemetry(art)
    row = run_recorder.record(db, DS, "run-1", art)
    assert row["run_status"] == "failed" and row["golden_status"] == "missing"
    golden = {"run_id": "run-1", "status": "passed", "asked": 7, "counts": {"wrong": 0, "refused": 1}}
    (art / DS / "golden.json").write_text(json.dumps(golden))
    row = run_recorder.record(db, DS, "run-1", art)
    assert row["run_status"] == "passed"
    assert (row["golden_status"], row["golden_question_count"], row["golden_refused_count"]) == ("passed", 7, 1)
    (art / DS / "golden.json").write_text(json.dumps({**golden, "status": "failed", "counts": {"wrong": 1}}))
    row = run_recorder.record(db, DS, "run-1", art)
    assert row["run_status"] == "failed" and "1 wrong answer" in row["run_problem_description"]
    skipped_refresh(art)
    (art / DS / "golden.json").unlink()
    assert run_recorder.record(db, DS, "run-1", art)["golden_status"] == "not run"


def test_record_fails_a_day_whose_telemetry_failed_or_never_reported(build):
    db, art = build
    write_results(art, results("pass"))
    gate(db, art, "run-1")
    publish(db, art)
    skipped_refresh(art)
    assert run_recorder.record(db, DS, "run-1", art)["telemetry_status"] == "passed"
    telemetry(art, status="skipped")
    assert run_recorder.record(db, DS, "run-1", art)["run_status"] == "passed"
    telemetry(art, status="failed")
    row = run_recorder.record(db, DS, "run-1", art)
    assert row["run_status"] == "failed" and "telemetry landing: boom" in row["run_problem_description"]
    (art / DS / "telemetry.json").unlink()
    assert run_recorder.record(db, DS, "run-1", art)["telemetry_status"] == "missing"


def test_snapshot_keeps_warehouse_and_mart_with_comments(build):
    db, art = build
    con = duckdb.connect(str(db))
    con.execute("comment on table data_mart_layer.rpt__sales__orders__daily is 'Orders per day.'")
    con.execute("comment on column data_mart_layer.rpt__sales__orders__daily.order_count is 'Orders that day.'")
    con.close()
    doc = publish(db, art)
    served = art.parent / "serve" / "analytics.duckdb"
    assert served.exists() and (art.parent / "serve" / f"analytics-{DS}.duckdb").exists()
    con = duckdb.connect(str(served), read_only=True)
    try:
        schemas = {r[0] for r in con.execute("select schema_name from duckdb_tables()").fetchall()}
        tcomment = con.execute("select comment from duckdb_tables() where table_name = 'rpt__sales__orders__daily'").fetchone()[0]
        ccomment = con.execute("select comment from duckdb_columns() where column_name = 'order_count'").fetchone()[0]
        catalog = con.execute("select current_database()").fetchone()[0]
    finally:
        con.close()
    assert schemas == {"data_warehouse_layer", "data_mart_layer"} and catalog == "analytics"
    assert (tcomment, ccomment) == ("Orders per day.", "Orders that day.")
    assert doc["tables"] == {"data_mart_layer.rpt__sales__orders__daily": 1, "data_warehouse_layer.fact__sales__orders": 1,
                             "data_warehouse_layer.fact__sales__refunds": 0}
    saved = json.loads((art / DS / "snapshot.json").read_text())
    assert saved["run_id"] == "run-1" and len(saved["snapshot_hash"]) == 64 and len(saved["schema_hash"]) == 64


def test_snapshot_keeps_the_last_seven_days(build):
    db, art = build
    serve = art.parent / "serve"
    for day in range(1, 10):
        snapshot.publish(db, f"2026-01-{day:02d}", "r", serve=serve, artifacts=art)
    dated = sorted(p.name for p in serve.glob("analytics-*.duckdb"))
    assert dated == [f"analytics-2026-01-{d:02d}.duckdb" for d in range(3, 10)]
    assert not list(serve.glob(".*"))


def test_schema_hash_changes_with_a_column_only(build):
    db, art = build
    first = publish(db, art)["schema_hash"]
    con = duckdb.connect(str(db))
    con.execute("insert into data_mart_layer.rpt__sales__orders__daily values (2)")
    con.close()
    assert publish(db, art)["schema_hash"] == first
    con = duckdb.connect(str(db))
    con.execute("alter table data_mart_layer.rpt__sales__orders__daily add column unit_count integer")
    con.close()
    assert publish(db, art)["schema_hash"] != first


T0 = dtm.datetime(2026, 1, 2, 3, 0, tzinfo=dtm.UTC)


def test_compile_done_waits_for_a_pass_after_the_restart():
    done = refresh_ontology.compile_done
    assert done({"running": True}, T0) == (False, None)
    assert done({"running": False, "last_success_at": "2026-01-02T02:00:00+00:00"}, T0) == (False, None)
    assert done({"running": False, "last_success_at": "2026-01-02T03:05:00+00:00"}, T0) == (True, None)
    finished, err = done({"running": False, "last_success_at": "2026-01-02T02:00:00Z",
                          "last_failure_at": "2026-01-02T03:01:00Z"}, T0)
    assert finished and "failed" in err


def test_refresh_skips_when_the_profile_is_down_and_says_so(tmp_path, monkeypatch):
    monkeypatch.setattr(refresh_ontology, "PROXY", "http://127.0.0.1:9")
    assert refresh_ontology.refresh(DS, "run-1", tmp_path) == refresh_ontology.SKIP
    report = json.loads((tmp_path / DS / "refresh.json").read_text())
    assert (report["run_id"], report["status"]) == ("run-1", "skipped")


def test_refresh_reports_a_failed_restart(tmp_path, monkeypatch):
    calls = []

    def fake(method, url, timeout=30):
        calls.append(url)
        return (200, {}) if url.endswith("/_ping") else (404, {})
    monkeypatch.setattr(refresh_ontology, "request", fake)
    assert refresh_ontology.refresh(DS, "run-1", tmp_path) == 1
    report = json.loads((tmp_path / DS / "refresh.json").read_text())
    assert report["status"] == "failed" and "restart wh-ingestion-service-1 failed: HTTP 404" in report["error"]


def test_record_fails_when_refresh_did_not_report_after_a_publish(build):
    db, art = build
    write_results(art, results("pass"))
    gate(db, art, "run-1")
    publish(db, art)
    row = run_recorder.record(db, DS, "run-1", art)
    assert row["run_status"] == "failed" and row["ontology_refresh_status"] == "missing"
    assert "ontology refresh did not report" in row["run_problem_description"]
    skipped_refresh(art, "run-old")                    # a report from an earlier run does not count
    assert run_recorder.record(db, DS, "run-1", art)["run_status"] == "failed"


def test_republishing_an_old_day_keeps_its_snapshot(build):
    db, art = build
    serve = art.parent / "serve"
    for day in range(10, 18):
        snapshot.publish(db, f"2026-01-{day:02d}", "r", serve=serve, artifacts=art)
    doc = snapshot.publish(db, "2026-01-02", "r", serve=serve, artifacts=art)
    dated = sorted(p.name for p in serve.glob("analytics-*.duckdb"))
    assert "analytics-2026-01-02.duckdb" in dated and len(dated) == 7
    assert dated[1:] == [f"analytics-2026-01-{d:02d}.duckdb" for d in range(12, 18)]
    assert len(doc["snapshot_hash"]) == 64
