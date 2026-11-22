"""check_naming: bad model names, folders and column names fail."""
import pytest

from helpers import check_naming as c
from helpers import dbtlib
from tests.governance.dbt_project import make_project, write

GOOD_COLS = "select order_id, amount_idr, {{ dbt_audit_columns() }} from {{ ref('staging__shop__orders') }}"


def errors(root):
    return c.check(dbtlib.load_models(root), root)


def test_repo_passes():
    assert c.check(dbtlib.load_models()) == []


def test_fixture_passes(tmp_path):
    assert errors(make_project(tmp_path)) == []


def at(layer: str, name: str, ext: str = "sql") -> str:
    return f"models/data_{layer}_layer/{name}/{name}.{ext}"


@pytest.mark.parametrize("rel, expect", [
    (at("warehouse", "orders_fact"), "is not dim__"),
    (at("warehouse", "stg__sales__orders"), "must start with dim__ or fact__"),
    (at("warehouse", "fact__shop__orders"), "is not a business domain"),
    (at("warehouse", "fact__sales__orders__daily"), "is not dim__"),
    (at("mart", "rpt__sales__orders__hourly"), "cadence 'hourly'"),
    (at("mart", "rpt__sales__orders"), "is not rpt__<domain>__<table>__<cadence>"),
    (at("mart", "rpt__sales__Refunds__daily"), "snake_case parts"),
    (at("staging", "staging__sales__orders"), "is not a source system"),
    ("models/intermediate/int__sales__orders/int__sales__orders.sql", "is not a layer folder"),
    ("models/staging/shop/staging__shop__orders.sql", "is not a layer folder"),
    ("models/data_warehouse_layer/fact__sales__payments.sql", "in its own folder"),
    ("models/data_warehouse_layer/sales/fact__sales__payments/fact__sales__payments.sql",
     "in its own folder"),
    ("models/data_warehouse_layer/fact__sales__payments/fact__sales__payment.sql",
     "named after its folder"),
    (at("lake", "shop__payments"), "lake folder holds only"),
])
def test_bad_layout_or_name_fails(tmp_path, rel, expect):
    root = make_project(tmp_path)
    write(root, rel, GOOD_COLS)
    errs = errors(root)
    assert any(expect in e for e in errs), errs


def test_other_file_types_fail(tmp_path):
    root = make_project(tmp_path)
    write(root, "models/data_mart_layer/rpt__sales__orders__daily/notes.txt", "x")
    assert any("only .sql, .yml and .md" in e for e in errors(root))


@pytest.mark.parametrize("table, expect", [
    ("orders", "is not <source>__<table>"),
    ("crm__orders", "is not a source system"),
])
def test_bad_lake_name_fails(tmp_path, table, expect):
    root = make_project(tmp_path)
    write(root, at("lake", table, "yml"),
          f"version: 2\nsources:\n- name: lake\n  tables:\n  - name: {table}\n")
    assert any(expect in e for e in errors(root))


def test_lake_table_declared_elsewhere_fails(tmp_path):
    root = make_project(tmp_path)
    write(root, at("lake", "shop__refunds", "yml"),
          "version: 2\nsources:\n- name: lake\n  tables:\n  - name: shop__payments\n")
    errs = errors(root)
    assert any("'shop__payments' is declared in models/data_lake_layer/shop__payments/" in e
               for e in errs), errs
    assert any("declares no lake table 'shop__refunds'" in e for e in errs), errs


@pytest.mark.parametrize("column, expect", [
    ("OrderId", "not snake_case"),
    ("order__id", "not snake_case"),
    ("_secret", "leading _ is kept"),
    ("status", "too generic"),
    ("id", "too generic"),
    ("city", "too generic"),
    ("shipping_fee", "not a class word"),
    ("customer_email", "not a class word"),
    ("orders_total", "not a class word"),
    ("shipping_fee_quantity", "money column ends in its unit"),
])
def test_bad_column_fails(tmp_path, column, expect):
    root = make_project(tmp_path)
    write(root, at("warehouse", "fact__sales__payments"),
          f"select order_id, 1 as {column}, {{{{ dbt_audit_columns() }}}} "
          f"from {{{{ ref('staging__shop__orders') }}}}")
    errs = errors(root)
    assert any(expect in e for e in errs), errs


@pytest.mark.parametrize("column", ["refund_reason_code", "spend_date", "paid_at", "discount_pct",
                                    "cost_per_click_idr", "_dbt_updated_at", "payment_method_code",
                                    "order_count", "item_quantity", "is_current", "has_refund",
                                    "email_address", "customer_version_key", "line_number"])
def test_good_columns_pass(column):
    assert c.column_errors(column) == []


def test_class_words_come_from_the_registry():
    assert set(c.CLASS_WORDS) >= {"id", "at", "date", "idr", "pct", "count"}


def test_yaml_only_column_is_checked_too(tmp_path):
    root = make_project(tmp_path)
    rel = at("mart", "rpt__sales__orders__daily", "yml")
    write(root, rel, (root / rel).read_text() + "  - name: Total\n    description: x\n")
    assert any("'Total'" in e for e in errors(root))
