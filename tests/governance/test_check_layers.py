"""check_layers: a model that reads across layers the wrong way fails."""
from helpers import check_layers as c
from helpers import dbtlib
from tests.governance.dbt_project import make_project, write


def errors(root):
    return c.check(dbtlib.load_models(root), dbtlib.load_sources(root))


def test_repo_passes():
    assert c.check(dbtlib.load_models(), dbtlib.load_sources()) == []


def test_fixture_passes(tmp_path):
    assert errors(make_project(tmp_path)) == []


def test_mart_reading_staging_fails(tmp_path):
    root = make_project(tmp_path)
    write(root, "models/data_mart_layer/rpt__sales__orders__daily/rpt__sales__orders__daily.sql",
          "select order_id from {{ ref('staging__shop__orders') }}")
    assert any("mart reads staging model 'staging__shop__orders'" in e for e in errors(root))


def test_warehouse_reading_mart_fails(tmp_path):
    root = make_project(tmp_path)
    write(root, "models/data_warehouse_layer/fact__sales__orders/fact__sales__orders.sql",
          "select order_date from {{ ref('rpt__sales__orders__daily') }}")
    assert any("warehouse reads mart model" in e for e in errors(root))


def test_warehouse_reading_the_lake_fails(tmp_path):
    root = make_project(tmp_path)
    write(root, "models/data_warehouse_layer/fact__sales__orders/fact__sales__orders.sql",
          "select order_id from {{ source('lake', 'shop__orders') }}")
    assert any("only staging reads the lake" in e for e in errors(root))


def test_staging_reading_a_model_fails(tmp_path):
    root = make_project(tmp_path)
    write(root, "models/data_staging_layer/staging__shop__orders/staging__shop__orders.sql",
          "select order_id from {{ ref('fact__sales__orders') }}")
    errs = errors(root)
    assert any("staging reads warehouse model" in e for e in errs)
    assert any("staging reads exactly source('lake', 'shop__orders')" in e for e in errs)


def test_staging_reading_another_lake_table_fails(tmp_path):
    root = make_project(tmp_path)
    write(root, "models/data_staging_layer/staging__shop__orders/staging__shop__orders.sql",
          "select a.order_id from {{ source('lake', 'shop__orders') }} a "
          "join {{ source('lake', 'shop__payments') }} p using (order_id)")
    errs = errors(root)
    assert any("staging reads exactly" in e for e in errs)
    assert any("'shop__payments') is not declared" in e for e in errs)


def test_ref_to_missing_model_fails(tmp_path):
    root = make_project(tmp_path)
    write(root, "models/data_mart_layer/rpt__sales__orders__daily/rpt__sales__orders__daily.sql",
          "select order_id from {{ ref('fact__sales__nothing') }}")
    assert any("names no model" in e for e in errors(root))


def test_warehouse_reading_warehouse_passes(tmp_path):
    root = make_project(tmp_path)
    write(root, "models/data_warehouse_layer/dim__sales__orders/dim__sales__orders.sql",
          "select order_id from {{ ref('fact__sales__orders') }}")
    assert errors(root) == []
