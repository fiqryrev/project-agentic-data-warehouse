"""check_bundle: a model without YAML, docs, matching columns or a key test fails."""
from helpers import check_bundle as c
from helpers import dbtlib
from tests.governance.dbt_project import FACT_YML, MART_YML, STAGING_YML, make_project, write

FACT = "models/warehouse/sales/_warehouse__sales.yml"


def errors(root):
    return c.check(dbtlib.load_models(root), root)


def test_repo_passes():
    assert c.check(dbtlib.load_models()) == []


def test_fixture_passes(tmp_path):
    assert errors(make_project(tmp_path)) == []


def test_model_without_yaml_fails(tmp_path):
    root = make_project(tmp_path)
    write(root, "models/warehouse/sales/dim__sales__customers.sql",
          "select customer_id, {{ dbt_audit_columns() }} from {{ ref('staging__shop__orders') }}")
    assert any("dim__sales__customers.sql: no YAML entry" in e for e in errors(root))


def test_missing_descriptions_fail(tmp_path):
    yml = FACT_YML.replace("  description: Current state of each order.\n", "") \
                  .replace("    description: Latest status.\n", "")
    errs = errors(make_project(tmp_path, **{FACT.replace("/", "__S__"): yml}))
    assert any("no model description" in e for e in errs)
    assert any("'order_status' has no description" in e for e in errs)


def test_column_missing_from_yaml_fails(tmp_path):
    yml = FACT_YML.replace("  - name: amount_idr\n    description: Order amount, in rupiah.\n", "")
    errs = errors(make_project(tmp_path, **{FACT.replace("/", "__S__"): yml}))
    assert any("'amount_idr' is output by the SQL but not in the YAML" in e for e in errs)


def test_yaml_column_not_in_sql_fails(tmp_path):
    yml = FACT_YML + "  - name: customer_id\n    description: Customer id.\n"
    errs = errors(make_project(tmp_path, **{FACT.replace("/", "__S__"): yml}))
    assert any("'customer_id' is in the YAML but the SQL does not output it" in e for e in errs)


def test_select_star_cannot_be_checked(tmp_path):
    root = make_project(tmp_path)
    write(root, "models/warehouse/sales/fact__sales__orders.sql",
          "select * from {{ ref('staging__shop__orders') }}")
    assert any("uses *; list the columns" in e for e in errors(root))


def test_unaliased_expression_fails(tmp_path):
    root = make_project(tmp_path)
    write(root, "models/mart/sales/rpt__sales__orders__daily.sql",
          "select order_date, count(*), sum(amount_idr) as amount_idr, {{ dbt_audit_columns() }} "
          "from {{ ref('fact__sales__orders') }} group by 1")
    assert any("has no alias" in e for e in errors(root))


def test_no_key_test_fails(tmp_path):
    yml = MART_YML.replace("    data_tests:\n    - unique\n    - not_null\n", "")
    errs = errors(make_project(tmp_path, **{"models__S__mart__S__sales__S___mart__sales.yml": yml}))
    assert any("no key test on the grain" in e for e in errs)


def test_unique_alone_is_not_a_key_test(tmp_path):
    yml = MART_YML.replace("    - not_null\n", "")
    errs = errors(make_project(tmp_path, **{"models__S__mart__S__sales__S___mart__sales.yml": yml}))
    assert any("no key test on the grain" in e for e in errs)


def test_model_level_unique_combination_counts(tmp_path):
    assert "unique_combination" in STAGING_YML
    assert c.has_grain_test({"data_tests": [{"unique_combination": {}}]})


def test_yaml_in_another_folder_fails(tmp_path):
    root = make_project(tmp_path, **{FACT.replace("/", "__S__"): None})
    write(root, "models/warehouse/_all.yml", FACT_YML)
    assert any("keep it in the model's folder" in e for e in errors(root))


def test_yaml_without_sql_fails(tmp_path):
    yml = MART_YML.replace("rpt__sales__orders__daily", "rpt__sales__refunds__daily")
    root = make_project(tmp_path)
    write(root, "models/mart/sales/_mart__refunds.yml", yml)
    assert any("'rpt__sales__refunds__daily' has no SQL model" in e for e in errors(root))
