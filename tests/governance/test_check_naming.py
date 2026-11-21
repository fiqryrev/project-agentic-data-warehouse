"""check_naming: bad model names, folders and column names fail."""
import pytest

from helpers import check_naming as c
from helpers import dbtlib
from tests.governance.dbt_project import make_project, write

GOOD_COLS = "select order_id, amount_idr, {{ dbt_audit_columns() }} from {{ ref('staging__shop__orders') }}"


def errors(root):
    return c.check(dbtlib.load_models(root))


def test_repo_passes():
    assert c.check(dbtlib.load_models()) == []


def test_fixture_passes(tmp_path):
    assert errors(make_project(tmp_path)) == []


@pytest.mark.parametrize("rel, expect", [
    ("models/warehouse/sales/orders_fact.sql", "is not dim__"),
    ("models/warehouse/sales/stg__sales__orders.sql", "must start with dim__ or fact__"),
    ("models/warehouse/sales/fact__finance__orders.sql", "does not match folder 'sales'"),
    ("models/warehouse/shop/fact__shop__orders.sql", "is not a business domain"),
    ("models/mart/sales/rpt__sales__orders__hourly.sql", "cadence 'hourly'"),
    ("models/mart/sales/rpt__sales__orders.sql", "is not rpt__<domain>__<table>__<cadence>"),
    ("models/mart/sales/rpt__sales__Refunds__daily.sql", "snake_case parts"),
    ("models/staging/sales/staging__sales__orders.sql", "is not a source system"),
    ("models/intermediate/sales/int__sales__orders.sql", "models live under"),
    ("models/warehouse/fact__sales__orders2.sql", "exactly one folder deep"),
])
def test_bad_model_name_fails(tmp_path, rel, expect):
    root = make_project(tmp_path)
    write(root, rel, GOOD_COLS)
    errs = errors(root)
    assert any(expect in e for e in errs), errs


@pytest.mark.parametrize("column, expect", [
    ("OrderId", "not snake_case"),
    ("order__id", "not snake_case"),
    ("_secret", "leading _ is kept"),
    ("status", "too generic"),
    ("id", "too generic"),
    ("shipping_fee", "money column ends in its unit"),
    ("net_revenue", "money column ends in its unit"),
])
def test_bad_column_fails(tmp_path, column, expect):
    root = make_project(tmp_path)
    write(root, "models/warehouse/sales/fact__sales__payments.sql",
          f"select order_id, 1 as {column}, {{{{ dbt_audit_columns() }}}} "
          f"from {{{{ ref('staging__shop__orders') }}}}")
    errs = errors(root)
    assert any(expect in e for e in errs), errs


@pytest.mark.parametrize("column", ["refund_reason", "spend_date", "paid_at", "discount_pct",
                                    "cost_per_click_idr", "_dbt_updated_at", "payment_method"])
def test_good_columns_pass(column):
    assert c.column_errors(column) == []


def test_yaml_only_column_is_checked_too(tmp_path):
    root = make_project(tmp_path)
    yml = (root / "models/mart/sales/_mart__sales.yml").read_text()
    write(root, "models/mart/sales/_mart__sales.yml",
          yml + "  - name: Total\n    description: x\n")
    assert any("'Total'" in e for e in errors(root))
