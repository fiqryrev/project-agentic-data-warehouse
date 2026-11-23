"""compare-providers: candidates, summary, report and experiment attributes, without a network."""
import datetime as dtm

from llm import ask as ak
from llm import compare as c
from llm import golden as g

T0 = dtm.datetime(2026, 11, 22, 10, tzinfo=dtm.UTC)


def result(qid, verdict, cost):
    a = ak.Answer("q", T0, T0 + dtm.timedelta(seconds=20))
    a.calls = {"cost_usd": cost, "call_count": 10}
    return g.Result(g.Question(qid, "q", "select 1"), a, verdict, "", True, "", [[1]])


def test_candidates_are_gateway_alias_pairs_in_the_gateway_config():
    from pathlib import Path

    import yaml
    cfg = yaml.safe_load((Path(__file__).resolve().parents[2] / "infra/llm-gateway/config.yaml").read_text())
    aliases = {m["model_name"] for m in cfg["model_list"]}
    assert c.CANDIDATES[c.DEFAULT] == ("openai/adw-reasoning", "openai/adw-non-reasoning")
    assert all(set(pair) <= aliases for pair in c.CANDIDATES.values())


def test_summary_counts_cost_per_correct_and_p95():
    rs = [result("g-1", "exact_match", 0.01), result("g-2", "refused", 0.03), result("g-3", "within_tolerance", 0.02)]
    s = c.summarise(rs, [100.0, 200.0, 300.0, 4000.0])
    assert (s["correct"], s["refused"], s["accuracy_pct"], s["cost_usd"], s["cost_per_correct_usd"]) == (2, 1, 66.7, 0.06, 0.03)
    assert 3000 < s["p95_latency_ms"] <= 4000
    assert c.summarise([result("g-1", "refused", 0.01)], [])["cost_per_correct_usd"] is None


def test_report_lists_only_changed_verdicts():
    rows = {k: c.summarise([result("g-1", v, 0.01)], [100.0]) for k, v in (("nvidia", "exact_match"), ("openrouter", "refused"))}
    text = c.report("compare-x", "2026-01-12", rows, {"nvidia": {"g-1": "exact_match", "g-2": "wrong"},
                                                      "openrouter": {"g-1": "refused", "g-2": "wrong"}}, c.CANDIDATES)
    assert "| g-1 | exact_match | refused |" in text and "| g-2 |" not in text
    assert "| nvidia | `openai/adw-reasoning`, `openai/adw-non-reasoning` | 1 | 1 |" in text


def test_experiment_attrs_tie_an_answer_to_the_dataset_item():
    a = c.experiment_attrs("compare-x", "openrouter", c.CANDIDATES["openrouter"], "ds1", "golden-g-1",
                           result("g-1", "wrong", 0.0), "span1")
    assert a["langfuse.experiment.name"] == "compare-x-openrouter" and a["langfuse.experiment.item.id"] == "golden-g-1"
    assert a["langfuse.experiment.dataset.id"] == "ds1" and a["langfuse.experiment.item.root_observation_id"] == "span1"


def test_reports_go_to_the_gitignored_data_folder():
    """M5 (#58): run reports are working output; one worth citing is copied to docs/runs/."""
    import subprocess

    from llm import compare
    assert compare.REPORTS.as_posix() == "data/runs"
    assert subprocess.run(["git", "check-ignore", "-q", "data/runs/x.md"]).returncode == 0


def test_every_cited_run_report_is_in_git():
    """Codex review on #61: worknotes and reports cite runs by id (`compare-20261122T1238`), and a
    figure must keep its source (rule 5). Any cited run id has its report in docs/runs/."""
    import re
    import subprocess
    from pathlib import Path
    repo = Path(__file__).resolve().parents[2]
    files = subprocess.run(["git", "ls-files", "*.md"], cwd=repo, capture_output=True, text=True,
                           check=True).stdout.split()
    cited = set()
    for f in files:
        if not (repo / f).is_file():
            continue
        cited |= set(re.findall(r"\b((?:compare|refusals)-\d{8}(?:T\d{4})?)\b", (repo / f).read_text(encoding="utf-8")))
    missing = sorted(c for c in cited if not (repo / "docs" / "runs" / f"{c}.md").exists())
    assert cited and not missing, missing
