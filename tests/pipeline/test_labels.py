"""label-prs: labels grouped from scores, routed by verdict, written as entries and golden questions."""
import yaml

from helpers import check_golden
from helpers.govlib import REPO
from llm import labels as L

T = "b" * 32
SCORES = [
    {"traceId": T, "authorUserId": None, "name": "verdict", "stringValue": "wrong_definition", "source": "API", "timestamp": "2026-11-22T10:00:00Z"},
    {"traceId": T, "authorUserId": None, "name": "note", "stringValue": "revenue means net_revenue_idr", "timestamp": "2026-11-22T10:00:01Z"},
    {"traceId": T, "authorUserId": None, "name": "golden_verdict", "stringValue": "wrong", "timestamp": "2026-11-22T09:00:00Z"},
    {"traceId": "c" * 32, "authorUserId": "u1", "name": "note", "stringValue": "no verdict yet", "timestamp": "2026-11-22T10:00:00Z"},
]
ANSWER = {"question": "What was the revenue on 2026-01-05?", "answer": "833,000,000", "golden_id": None,
          "sql": "select ledger_gross_idr from data_mart_layer.rpt__finance__revenue__daily where revenue_date = '2026-01-05'"}


def test_labels_group_by_trace_and_labeller_and_need_a_verdict():
    labs = L.labels_from_scores(SCORES)
    assert len(labs) == 1
    lab = labs[0]
    assert (lab["labeler"], lab["verdict"], lab["note"]) == ("api", "wrong_definition", "revenue means net_revenue_idr")
    assert L.new_labels(labs, [{"trace_id": T, "labeler": "api"}]) == []


def test_verdicts_route_to_their_change():
    route = {v: L.outcome_of({"verdict": v}, ANSWER) for v in
             ("correct", "wrong_definition", "wrong_filter", "wrong_grain", "wrong_number", "refused_wrongly")}
    assert route == {"correct": "golden", "wrong_definition": "knowledge", "wrong_filter": "knowledge",
                     "wrong_grain": "issue", "wrong_number": "issue", "refused_wrongly": "recorded"}
    assert L.outcome_of({"verdict": "correct"}, {**ANSWER, "golden_id": "g-0001"}) == "already_golden"


def test_knowledge_entry_has_the_da_sections_and_cites_its_sql():
    lab = {**L.labels_from_scores(SCORES)[0], "correct_sql": "select net_revenue_idr from x"}
    text = L.knowledge_entry("da-0099", lab, ANSWER, "2026-01-10", [(718362280,)], "2026-11-22")
    front, body = text.split("---\n", 2)[1:]
    meta = yaml.safe_load(front)
    assert meta["id"] == "da-0099" and meta["evidence"] == [f"evals/labels/processed.yaml::{T}"]
    assert [s for s in ("## Meaning", "## Counts", "## Terms", "## Data quality") if s in body] == \
        ["## Meaning", "## Counts", "## Terms", "## Data quality"]
    assert "```sql\nselect net_revenue_idr from x\n```" in body and "718362280" in body


def test_golden_from_a_correct_label_passes_check_golden(tmp_path):
    lab = {"verdict": "correct", "trace_id": T}
    doc = L.golden_doc("g-0099", lab, ANSWER, "2026-01-10")
    assert doc["needs_day"] == "2026-01-05"
    path = tmp_path / "g-0099-revenue.yaml"
    path.write_text(yaml.dump(doc, Dumper=L._Block, sort_keys=False))
    assert "reference_sql: |" in path.read_text()
    models = check_golden.layer_models(REPO)
    assert check_golden.check_question(path.relative_to(tmp_path), yaml.safe_load(path.read_text()), models, set()) == []
