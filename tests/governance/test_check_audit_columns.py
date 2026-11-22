"""check_audit_columns: a lake table or model without its audit columns fails."""
import duckdb

from helpers import check_audit_columns as c
from helpers import dbtlib
from tests.governance.dbt_project import make_project, write

LAKE_OK = ("create table lake.shop__orders (order_id int, _dt date, _source_file varchar, "
           "_loaded_at timestamp, _batch_id varchar)")


def lake(*ddl):
    con = duckdb.connect()
    con.execute("create schema lake")
    for stmt in ddl:
        con.execute(stmt)
    return con


def test_repo_passes_on_a_fresh_lake(tmp_path):
    db = tmp_path / "audit.duckdb"
    c.build_lake(db)
    con = duckdb.connect(str(db), read_only=True)
    try:
        assert c.check(con) == []
    finally:
        con.close()


def test_fixture_passes(tmp_path):
    assert c.check(lake(LAKE_OK), make_project(tmp_path)) == []


def test_lake_table_without_audit_columns_fails(tmp_path):
    con = lake(LAKE_OK, "create table lake.shop__payments (payment_id int, _dt date)")
    errs = c.check(con, make_project(tmp_path))
    assert errs == ["lake.shop__payments: missing audit columns _source_file, _loaded_at, _batch_id"]


def test_declared_source_missing_from_lake_fails(tmp_path):
    con = lake("create table lake.shop__refunds (refund_id int, _dt date, _source_file varchar, "
               "_loaded_at timestamp, _batch_id varchar)")
    errs = c.check(con, make_project(tmp_path))
    assert any("lake.shop__orders does not exist" in e for e in errs)


def test_empty_lake_fails(tmp_path):
    assert c.check(lake(), make_project(tmp_path))[0] == "the lake has no tables"


def test_warehouse_model_without_audit_macro_fails(tmp_path):
    root = make_project(tmp_path)
    write(root, "models/data_warehouse_layer/fact__sales__orders/fact__sales__orders.sql",
          "select order_id, order_status from {{ ref('staging__shop__orders') }}")
    errs = c.model_errors(dbtlib.load_models(root))
    assert errs == ["models/data_warehouse_layer/fact__sales__orders/fact__sales__orders.sql: warehouse model does not "
                    "output _dbt_invocation_id, _dbt_updated_at (add {{ dbt_audit_columns() }})"]


def test_staging_model_dropping_dt_fails(tmp_path):
    root = make_project(tmp_path)
    write(root, "models/data_staging_layer/staging__shop__orders/staging__shop__orders.sql",
          "select order_id from {{ source('lake', 'shop__orders') }}")
    errs = c.model_errors(dbtlib.load_models(root))
    assert any("staging model does not output _dt" in e for e in errs)


def test_mart_needs_no_audit_columns(tmp_path):
    root = make_project(tmp_path)
    write(root, "models/data_mart_layer/rpt__sales__orders__daily/rpt__sales__orders__daily.sql",
          "select order_date from {{ ref('fact__sales__orders') }}")
    assert c.model_errors(dbtlib.load_models(root)) == []


def test_main_reads_an_existing_file(tmp_path, capsys):
    db = tmp_path / "x.duckdb"
    con = duckdb.connect(str(db))
    con.execute("create schema lake")
    con.execute("create table lake.shop__orders (order_id int)")
    con.close()
    assert c.main(["--db", str(db), "--project", str(make_project(tmp_path / "p"))]) == 1
    assert "missing audit columns" in capsys.readouterr().out
