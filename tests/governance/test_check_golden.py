"""check_golden: a golden question that cannot be asked or scored fails."""
from pathlib import Path

import pytest
import yaml

from helpers import check_golden as c
from helpers.govlib import REPO

MODELS = {"data_mart_layer": {"rpt__finance__revenue__daily"}, "data_warehouse_layer": {"fact__sales__orders"}}
ENTRIES = {"da-0001"}
GOOD = {"id": "g-0001", "question": "Net revenue on 2026-01-05?", "kind": "scalar", "needs_day": "2026-01-05",
        "reference_sql": "select net_revenue_idr from data_mart_layer.rpt__finance__revenue__daily "
                         "where revenue_date = date '2026-01-05'"}


def errors(**change):
    doc = {**GOOD, **change}
    return c.check_question(Path("evals/golden/g-0001-x.yaml"), {k: v for k, v in doc.items() if v is not None},
                            MODELS, ENTRIES)


def test_repo_passes():
    assert c.check(REPO) == []


def test_good_question_passes():
    assert errors() == []


@pytest.mark.parametrize("change, expect", [
    ({"id": "g-1"}, "is not g-NNNN"),
    ({"id": "g-0002"}, "file name does not start with g-0002-"),
    ({"kind": "table"}, "is not scalar or rows"),
    ({"kind": "rows"}, "needs a key column"),
    ({"tolerance_pct": 150}, "tolerance_pct"),
    ({"needs_day": "soon"}, "is not a date"),
    ({"question": None}, "missing field question"),
    ({"owner": "x"}, "unknown field owner"),
    ({"reference_sql": "delete from data_mart_layer.rpt__finance__revenue__daily"}, "must start with select"),
    ({"reference_sql": "select 1 from data_mart_layer.rpt__finance__revenue__daily; select 2"}, "more than one"),
    ({"reference_sql": "with x as (select 1) insert into data_mart_layer.rpt__finance__revenue__daily select * from x"},
     "only reads"),
    ({"reference_sql": "select * from data_lake_layer.shop__orders"}, "is not served"),
    ({"reference_sql": "select * from data_mart_layer.rpt__nothing__daily"}, "is not a dbt model"),
    ({"reference_sql": "select 1"}, "reads no data_warehouse_layer"),
    ({"reference_sql": "select count(*) from data_warehouse_layer.fact__sales__orders where order_status = 'cancelled'"},
     "need evidence"),
    ({"evidence": ["da-9999"]}, "is not a da- entry"),
])
def test_bad_question_fails(change, expect):
    assert any(expect in e for e in errors(**change)), errors(**change)


def test_iso_date_string_needs_no_evidence():
    sql = "select order_count from data_mart_layer.rpt__finance__revenue__daily where revenue_date = '2026-01-03'"
    assert errors(reference_sql=sql) == []


def test_literal_with_evidence_passes():
    sql = "select count(*) from data_warehouse_layer.fact__sales__orders where order_status = 'cancelled'"
    assert errors(reference_sql=sql, evidence=["da-0001"]) == []


def test_duplicate_ids_fail(tmp_path):
    (tmp_path / "evals" / "golden").mkdir(parents=True)
    for name in ("g-0001-a.yaml", "g-0001-b.yaml"):
        (tmp_path / "evals" / "golden" / name).write_text(yaml.safe_dump(GOOD))
    model = tmp_path / "dbt" / "models" / "data_mart_layer" / "rpt__finance__revenue__daily"
    model.mkdir(parents=True)
    out = c.check(tmp_path)
    assert any("also in g-0001-a.yaml" in e for e in out), out
