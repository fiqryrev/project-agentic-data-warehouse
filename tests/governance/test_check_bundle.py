"""check_bundle: a table without its YAML, doc, matching columns or key test fails."""
import pytest

from helpers import check_bundle as c
from helpers import dbtlib
from tests.governance.dbt_project import (FACT, FACT_YML, LAKE, MART, MART_YML, SECTIONS,
                                          STAGING_YML, doc, make_project, write)


def errors(root):
    return c.check(dbtlib.load_models(root), root)


def test_repo_passes():
    assert c.check(dbtlib.load_models()) == []


def test_fixture_passes(tmp_path):
    assert errors(make_project(tmp_path)) == []


def test_model_without_yaml_fails(tmp_path):
    root = make_project(tmp_path)
    name = "dim__sales__customers"
    write(root, f"models/data_warehouse_layer/{name}/{name}.sql",
          "select customer_id, {{ dbt_audit_columns() }} from {{ ref('staging__shop__orders') }}")
    assert any(f"{name}.sql: no YAML entry" in e for e in errors(root))


def test_yaml_in_another_file_fails(tmp_path):
    root = make_project(tmp_path, {f"{FACT}.yml": None})
    write(root, "models/data_warehouse_layer/fact__sales__orders/schema.yml", FACT_YML)
    assert any(f"keep it in {FACT}.yml" in e for e in errors(root))


def test_yaml_without_sql_fails(tmp_path):
    root = make_project(tmp_path)
    write(root, f"{MART}.yml", MART_YML + MART_YML.split("models:\n")[1]
          .replace("rpt__sales__orders__daily", "rpt__sales__refunds__daily"))
    assert any("'rpt__sales__refunds__daily' has no SQL model" in e for e in errors(root))


def test_description_must_be_the_doc(tmp_path):
    yml = FACT_YML.replace("""'{{ doc("fact__sales__orders") }}'""", "Current state of each order.")
    errs = errors(make_project(tmp_path, {f"{FACT}.yml": yml}))
    assert any("""the description is '{{ doc("fact__sales__orders") }}'""" in e for e in errs), errs


def test_doc_of_another_table_fails(tmp_path):
    yml = FACT_YML.replace('doc("fact__sales__orders")', 'doc("rpt__sales__orders__daily")')
    errs = errors(make_project(tmp_path, {f"{FACT}.yml": yml}))
    assert any("the description is" in e for e in errs), errs


def test_missing_doc_fails(tmp_path):
    errs = errors(make_project(tmp_path, {f"{FACT}.md": None}))
    assert any(f"no doc; write {FACT}.md" in e for e in errs), errs


def test_lake_table_needs_its_doc(tmp_path):
    errs = errors(make_project(tmp_path, {f"{LAKE}.md": None}))
    assert any(f"no doc; write {LAKE}.md" in e for e in errs), errs


@pytest.mark.parametrize("text, expect", [
    (doc("fact__sales__orders", SECTIONS[:-1]), "missing section(s): ## Change History"),
    (doc("fact__sales__orders", (SECTIONS[1], SECTIONS[0]) + SECTIONS[2:]), "out of order"),
    (doc("fact__sales__orders", opening=""), "no opening paragraph"),
    (doc("fact__sales__orders", opening="## Overview"), "no opening paragraph"),
    (doc("fact__sales__orders").replace("About grain.", ""), "'## Grain' is empty"),
    (doc("fact__sales__orders").replace("| 1.0.0 | 2026-11-22 | data-engineering | First version. |", ""),
     "Change History has no row"),
    (doc("fact__sales__orders").replace("About grain.", "{{ ref('x') }}"), "'{{' inside"),
    (doc("fact__sales__orders") + "trailing text\n", "text outside the docs block"),
    (doc("fact__sales__orders") + doc("fact__sales__orders"), "holds 2 docs blocks"),
    (doc("fact__sales__orders").replace("docs fact__sales__orders", "docs fact_orders"),
     "named 'fact_orders'"),
])
def test_bad_doc_fails(tmp_path, text, expect):
    errs = errors(make_project(tmp_path, {f"{FACT}.md": text}))
    assert any(expect in e for e in errs), errs


def test_extra_section_is_allowed(tmp_path):
    text = doc("fact__sales__orders", SECTIONS[:2] + ("Column Groups",) + SECTIONS[2:])
    assert errors(make_project(tmp_path, {f"{FACT}.md": text})) == []


def test_missing_column_description_fails(tmp_path):
    yml = FACT_YML.replace("    description: Latest status.\n", "")
    errs = errors(make_project(tmp_path, {f"{FACT}.yml": yml}))
    assert any("'order_status' has no description" in e for e in errs)


def test_column_missing_from_yaml_fails(tmp_path):
    yml = FACT_YML.replace("  - name: amount_idr\n    description: Order amount, in rupiah.\n", "")
    errs = errors(make_project(tmp_path, {f"{FACT}.yml": yml}))
    assert any("'amount_idr' is output by the SQL but not in the YAML" in e for e in errs)


def test_yaml_column_not_in_sql_fails(tmp_path):
    yml = FACT_YML + "  - name: customer_id\n    description: Customer id.\n"
    errs = errors(make_project(tmp_path, {f"{FACT}.yml": yml}))
    assert any("'customer_id' is in the YAML but the SQL does not output it" in e for e in errs)


def test_select_star_cannot_be_checked(tmp_path):
    root = make_project(tmp_path)
    write(root, f"{FACT}.sql", "select * from {{ ref('staging__shop__orders') }}")
    assert any("uses *; list the columns" in e for e in errors(root))


def test_unaliased_expression_fails(tmp_path):
    root = make_project(tmp_path)
    write(root, f"{MART}.sql",
          "select order_date, count(*), sum(amount_idr) as amount_idr, {{ dbt_audit_columns() }} "
          "from {{ ref('fact__sales__orders') }} group by 1")
    assert any("has no alias" in e for e in errors(root))


def test_no_key_test_fails(tmp_path):
    yml = MART_YML.replace("    data_tests:\n    - unique\n    - not_null\n", "")
    errs = errors(make_project(tmp_path, {f"{MART}.yml": yml}))
    assert any("no key test on the grain" in e for e in errs)


def test_unique_alone_is_not_a_key_test(tmp_path):
    yml = MART_YML.replace("    - not_null\n", "")
    errs = errors(make_project(tmp_path, {f"{MART}.yml": yml}))
    assert any("no key test on the grain" in e for e in errs)


def test_model_level_unique_combination_counts():
    assert "unique_combination" in STAGING_YML
    assert c.has_grain_test({"data_tests": [{"unique_combination": {}}]})


def test_if_else_branches_with_different_columns_fail(tmp_path):
    root = make_project(tmp_path)
    write(root, f"{MART}.sql",
          "{% if target.name == 'ci' %} select order_date from {{ ref('fact__sales__orders') }}\n"
          "{% else %} select order_date, count(*) as order_count, sum(amount_idr) as amount_idr, "
          "{{ dbt_audit_columns() }} from {{ ref('fact__sales__orders') }} group by 1 {% endif %}")
    assert any("if/else branches output different columns" in e for e in errors(root))


def test_incremental_filter_and_config_pass(tmp_path):
    root = make_project(tmp_path)
    sql = (root / f"{MART}.sql").read_text()
    write(root, f"{MART}.sql",
          "{{ config(materialized='incremental') }}\n" + sql.replace(
              "group by 1", "{% if is_incremental() %} where order_date > "
              "(select max(order_date) from {{ this }}) {% endif %}\ngroup by 1"))
    assert errors(root) == []


def test_for_loop_and_two_statements_fail(tmp_path):
    root = make_project(tmp_path)
    write(root, f"{MART}.sql",
          "select {% for c in ['order_date'] %}{{ c }}{% endfor %} from {{ ref('fact__sales__orders') }}")
    write(root, f"{FACT}.sql",
          "select order_id from {{ ref('staging__shop__orders') }}; select 1 as order_id")
    errs = errors(root)
    assert any("{% for %} loop cannot be read statically" in e for e in errs)
    assert any("renders to 2 statements" in e for e in errs)
