import datetime as dt
import json
import re
from pathlib import Path

import pytest

from helpers import ai_usage_footer as f
from helpers import check_pr_body

PRICING = f.load_pricing()


def assistant(mid, ts, model="claude-opus-5-5", effort="medium", inp=0, w5=0, w1=0, cr=0, out=0):
    return {
        "type": "assistant",
        "timestamp": ts,
        "effort": effort,
        "message": {
            "id": mid,
            "model": model,
            "usage": {
                "input_tokens": inp,
                "cache_creation_input_tokens": w5 + w1,
                "cache_creation": {"ephemeral_5m_input_tokens": w5, "ephemeral_1h_input_tokens": w1},
                "cache_read_input_tokens": cr,
                "output_tokens": out,
            },
        },
    }


def write_jsonl(path: Path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")


@pytest.fixture
def session(tmp_path):
    main = tmp_path / "sess-1.jsonl"
    write_jsonl(main, [
        {"type": "user", "timestamp": "2026-11-21T10:00:00Z", "message": {"content": "hi"}},
        # the same message id appears once per content block; it must be counted once
        assistant("m1", "2026-11-21T10:00:01Z", inp=10, w1=1_000_000, cr=0, out=100),
        assistant("m1", "2026-11-21T10:00:01Z", inp=10, w1=1_000_000, cr=0, out=100),
        assistant("m2", "2026-11-21T10:05:00Z", inp=5, w5=1_000_000, cr=2_000_000, out=900),
    ])
    write_jsonl(tmp_path / "sess-1" / "subagents" / "agent-a.jsonl", [
        {"type": "api-request", "params": {"output_config": {"effort": "low"}}},
        {**assistant("s1", "2026-11-21T10:02:00Z", model="claude-haiku-5-5", effort=None,
                     inp=1_000_000, out=1_000_000)},
    ])
    return main


def test_one_count_per_message_id_and_subagents(session):
    msgs = f.read_session(session)
    assert [m.id for m in msgs] == ["m1", "s1", "m2"]
    sub = next(m for m in msgs if m.id == "s1")
    assert sub.role == "subagent" and sub.effort == "low"


def test_each_class_priced_at_its_own_rate(session):
    body = f.render("Summary", pricing=PRICING, session_paths=[session], manual=[], priors=[],
                    harness="Claude Code")
    lines = dict(ln.split(": ", 1) for ln in re.search(r"```text\n(.*?)\n```", body, re.S)
                 .group(1).splitlines())
    # opus: 15 uncached * 4 + 1M 5m * 5 + 1M 1h * 8 + 2M read * 0.20 = 0.00006 + 5 + 8 + 0.40
    # haiku: 1M input * 0.10 = 0.10 ; input total = 13.50
    assert lines["Input Token Usage"] == "5,000,015 ($13.50) - Cache hit (2,000,000, $0.40)"
    # opus output 1,000 * 20 / 1M = 0.02 ; haiku 1M * 0.50 = 0.50
    assert lines["Output Token Usage"] == "1,001,000 ($0.52) - Cache hit (0, $0.00)"
    assert lines["Total Token"] == "6,001,015 ($14.02) - Cache hit (2,000,000, $0.40)"
    assert lines["Model Name"] == "claude-opus-5-5 (effort medium), claude-haiku-5-5 (effort low)"
    assert "3 requests, 1 session, 1 subagent" in lines["Metadata"]
    assert "list-price estimate, not money paid" in lines["Metadata"]
    assert check_pr_body.check_footer(body) == []


def test_footer_shape_is_fixed(session):
    body = f.render("", pricing=PRICING, session_paths=[session], manual=[], priors=[],
                    harness="Claude Code")
    lines = body.rstrip("\n").splitlines()
    assert lines[0] == "## AI usage" and lines[1] == "" and lines[2] == "```text"
    assert [ln.split(":")[0] for ln in lines[3:9]] == list(f.FOOTER_LABELS)
    assert lines[9] == "```" and lines[10].startswith("<!-- ai-usage-ledger: ")
    assert len(lines) == 11


def test_replaces_old_footer_and_watermark(session):
    old = "Summary\n\n🤖 Generated with [Claude Code](https://x)\n\n## AI usage\n\nold stuff\n"
    body = f.render(old, pricing=PRICING, session_paths=[session], manual=[], priors=[],
                    harness="Claude Code")
    assert body.count("## AI usage") == 1
    assert "Generated with" not in body and "old stuff" not in body
    assert body.startswith("Summary\n\n## AI usage")


def test_ledger_counts_only_new_messages(session):
    first = f.render("PR one", pricing=PRICING, session_paths=[session], manual=[], priors=[],
                     harness="Claude Code", until="2026-11-21T10:03:00Z")
    assert "2 requests" in first
    second = f.render("PR two", pricing=PRICING, session_paths=[session], manual=[],
                      priors=[first], harness="Claude Code")
    assert "1 request," in second and "since the previous footer" in second
    # re-rendering the same PR keeps its start, so it does not shrink to nothing
    again = f.render(second, pricing=PRICING, session_paths=[session], manual=[],
                     priors=[first], harness="Claude Code")
    assert "1 request," in again
    assert f.read_ledger(again)["sess-1"]["from"] == "2026-11-21T10:02:00Z"


def test_manual_usage_flags():
    usage = f.parse_usage_flag("model=claude-fable-5-2,effort=high,input=1000000,output=1000000,requests=3")
    body = f.render("x", pricing=PRICING, session_paths=[], manual=[usage], priors=[],
                    harness="Other Tool")
    assert "Harness Tool: Other Tool" in body
    assert "Model Name: claude-fable-5-2 (effort high)" in body
    assert "Total Token: 2,000,000 ($48.00)" in body
    assert "token counts passed as flags" in body


def test_unknown_model_fails_loudly():
    usage = f.parse_usage_flag("model=not-a-model,output=1")
    with pytest.raises(KeyError):
        f.render("x", pricing=PRICING, session_paths=[], manual=[usage], priors=[], harness="h")


def test_long_context_and_fast_rates():
    pricing = {"providers": {"p": {"source_url": "https://e", "verified_on": "2026-11-21", "models": {
        "m": {"input": 1, "cache_write_5m": 1, "cache_write_1h": 1, "cache_read": 1, "output": 1,
              "fast_multiplier": 6,
              "long_context": {"threshold_input_tokens": 100,
                               "rates": {"input": 2, "cache_write_5m": 2, "cache_write_1h": 2,
                                         "cache_read": 2, "output": 3}}}}}}}
    small = dict.fromkeys(f.CLASSES, 0) | {"input": 50, "output": 1_000_000}
    big = dict.fromkeys(f.CLASSES, 0) | {"input": 200, "output": 1_000_000}
    assert f.price_message(pricing, "m", small, fast=False)["output"] == 1
    assert f.price_message(pricing, "m", big, fast=False)["output"] == 3
    assert f.price_message(pricing, "m", small, fast=True)["output"] == 6


def test_check_prices_passes_on_repo_file():
    errors, _ = f.check_prices(PRICING, today=dt.date(2026, 11, 21))
    assert errors == []


def test_check_prices_catches_bad_file():
    bad = {"stale_after_days": 90, "providers": {"p": {
        "source_url": "http://not-https", "verified_on": "2099-01-01",
        "models": {"m": {"input": 1, "cache_write_5m": 0, "cache_read": -1, "output": "x"}}}}}
    errors, _ = f.check_prices(bad, today=dt.date(2026, 11, 21))
    text = "\n".join(errors)
    for needle in ("source_url", "in the future", "missing rate 'cache_write_1h'",
                   "'cache_write_5m' must be a positive", "'cache_read' must be",
                   "'output' must be"):
        assert needle in text


def test_check_prices_warns_when_stale():
    errors, warnings = f.check_prices(PRICING, today=dt.date(2027, 6, 1))
    assert errors == [] and warnings and "older than 90 days" in warnings[0]
