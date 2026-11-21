#!/usr/bin/env python3
"""Render the `## AI usage` footer of a pull request body (PLAN section 8.7).

    render --body-file <pr-body>   read the coding agent's session logs, price every token
                                   class at its own rate, and replace the footer in the body
    check-prices                   validate .agents/ai-usage/model-pricing.yaml

The footer always has the same shape: the heading, a fenced `text` block with six lines
(Harness Tool, Model Name, Input/Output/Total Token Usage, Metadata), then one hidden
ledger comment that records which part of each session was counted, so the next PR from the
same session counts only what came after.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
PRICING_FILE = REPO / ".agents" / "ai-usage" / "model-pricing.yaml"
CLASSES = ("input", "cache_write_5m", "cache_write_1h", "cache_read", "output")
INPUT_CLASSES = ("input", "cache_write_5m", "cache_write_1h", "cache_read")
HEADING = "## AI usage"
HEADING_RE = re.compile(r"^## AI usage[ \t]*$", re.M)
LEDGER_PREFIX = "<!-- ai-usage-ledger: "
LEDGER_RE = re.compile(r"<!--\s*ai-usage-ledger:\s*(\{.*?\})\s*-->", re.S)
WATERMARK_RE = re.compile(
    r"generated (with|by)\s*\[?\s*(claude|codex|cursor|copilot|chatgpt|gemini|aider)"
    r"|co-authored-by:",
    re.I,
)
FOOTER_LABELS = (
    "Harness Tool",
    "Model Name",
    "Input Token Usage",
    "Output Token Usage",
    "Total Token",
    "Metadata",
)


# --------------------------------------------------------------------------- pricing


def load_pricing(path: Path = PRICING_FILE) -> dict:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _is_positive_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def _check_rates(where: str, rates, errors: list[str]) -> None:
    if not isinstance(rates, dict):
        errors.append(f"{where}: rates must be a mapping")
        return
    for cls in CLASSES:
        if cls not in rates:
            errors.append(f"{where}: missing rate '{cls}'")
        elif not _is_positive_number(rates[cls]):
            errors.append(f"{where}: rate '{cls}' must be a positive number, got {rates[cls]!r}")


def check_prices(data: dict, today: dt.date | None = None) -> tuple[list[str], list[str]]:
    """Return (errors, warnings) for a parsed pricing file."""
    today = today or dt.date.today()
    errors: list[str] = []
    warnings: list[str] = []
    stale = data.get("stale_after_days")
    if not isinstance(stale, int) or isinstance(stale, bool) or stale <= 0:
        errors.append("stale_after_days must be a positive integer")
        stale = None
    providers = data.get("providers")
    if not isinstance(providers, dict) or not providers:
        errors.append("providers must be a non-empty mapping")
        return errors, warnings
    for pname, prov in providers.items():
        where = f"providers.{pname}"
        if not isinstance(prov, dict):
            errors.append(f"{where}: must be a mapping")
            continue
        url = prov.get("source_url")
        if not isinstance(url, str) or not url.startswith("https://"):
            errors.append(f"{where}: source_url must be an https URL of the official pricing page")
        verified = prov.get("verified_on")
        if isinstance(verified, str):
            try:
                verified = dt.date.fromisoformat(verified)
            except ValueError:
                verified = None
        if not isinstance(verified, dt.date):
            errors.append(f"{where}: verified_on must be a date (YYYY-MM-DD)")
        elif verified > today:
            errors.append(f"{where}: verified_on {verified} is in the future")
        elif stale and (today - verified).days > stale:
            warnings.append(
                f"{where}: prices verified on {verified}, older than {stale} days; re-check "
                f"{url}"
            )
        models = prov.get("models")
        if not isinstance(models, dict) or not models:
            errors.append(f"{where}: models must be a non-empty mapping")
            continue
        for mname, cfg in models.items():
            mwhere = f"{where}.models.{mname}"
            if not isinstance(cfg, dict):
                errors.append(f"{mwhere}: must be a mapping")
                continue
            unknown = set(cfg) - set(CLASSES) - {"fast_multiplier", "long_context"}
            if unknown:
                errors.append(f"{mwhere}: unknown keys {sorted(unknown)}")
            _check_rates(mwhere, {k: cfg.get(k) for k in CLASSES if k in cfg}, errors)
            if "fast_multiplier" in cfg and not _is_positive_number(cfg["fast_multiplier"]):
                errors.append(f"{mwhere}: fast_multiplier must be a positive number")
            if "long_context" in cfg:
                lc = cfg["long_context"]
                if not isinstance(lc, dict):
                    errors.append(f"{mwhere}.long_context: must be a mapping")
                    continue
                thr = lc.get("threshold_input_tokens")
                if not isinstance(thr, int) or isinstance(thr, bool) or thr <= 0:
                    errors.append(f"{mwhere}.long_context: threshold_input_tokens must be a positive integer")
                _check_rates(f"{mwhere}.long_context.rates", lc.get("rates"), errors)
    return errors, warnings


def find_model(pricing: dict, model: str) -> tuple[str, dict, dict]:
    """Return (provider name, provider block, model block) for a model id."""
    for pname, prov in (pricing.get("providers") or {}).items():
        models = prov.get("models") or {}
        if model in models:
            return pname, prov, models[model]
    raise KeyError(
        f"no price for model '{model}' in {PRICING_FILE.relative_to(REPO)}; add it from the "
        "provider's official pricing page"
    )


# --------------------------------------------------------------------------- transcripts


@dataclass
class Message:
    id: str
    model: str
    timestamp: str
    tokens: dict[str, int]
    effort: str | None
    role: str  # "main" or "subagent"
    source: str  # file name it came from
    fast: bool = False


def _parse_ts(ts: str | None) -> dt.datetime | None:
    if not ts:
        return None
    try:
        return dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def usage_to_tokens(usage: dict) -> dict[str, int]:
    """Split one API usage block into the five priced token classes."""
    created = int(usage.get("cache_creation_input_tokens") or 0)
    detail = usage.get("cache_creation") or {}
    w1h = int(detail.get("ephemeral_1h_input_tokens") or 0)
    w5m = int(detail.get("ephemeral_5m_input_tokens") or 0)
    # Anything not split by TTL is billed as a 5-minute write (the API default).
    w5m += max(created - w1h - w5m, 0)
    return {
        "input": int(usage.get("input_tokens") or 0),
        "cache_write_5m": w5m,
        "cache_write_1h": w1h,
        "cache_read": int(usage.get("cache_read_input_tokens") or 0),
        "output": int(usage.get("output_tokens") or 0),
    }


def session_files(main: Path) -> list[tuple[Path, str]]:
    files = [(main, "main")]
    sub_dir = main.with_suffix("") / "subagents"
    if sub_dir.is_dir():
        files += [(p, "subagent") for p in sorted(sub_dir.glob("*.jsonl"))]
    return files


def read_session(main: Path) -> list[Message]:
    """Read a Claude Code session (main transcript plus subagents), one entry per message id.

    Claude Code writes one line per content block, all carrying the same message id and
    usage; counting each line would multiply the tokens. The entry with the largest output
    count wins, which is the final usage of a streamed message.
    """
    messages: dict[str, Message] = {}
    for path, role in session_files(main):
        request_effort: str | None = None
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(rec, dict):
                    continue
                if rec.get("type") == "api-request":
                    params = rec.get("params") if isinstance(rec.get("params"), dict) else {}
                    eff = (params.get("output_config") or {}).get("effort")
                    request_effort = eff or request_effort
                    continue
                if rec.get("type") != "assistant":
                    continue
                msg = rec.get("message") or {}
                mid, usage, model = msg.get("id"), msg.get("usage"), msg.get("model")
                if not mid or not isinstance(usage, dict) or not model or model.startswith("<"):
                    continue
                effort = (
                    rec.get("effort")
                    or (rec.get("output_config") or {}).get("effort")
                    or (msg.get("output_config") or {}).get("effort")
                    or rec.get("perTurnEffort")
                    or request_effort
                )
                found = Message(
                    id=mid,
                    model=model,
                    timestamp=rec.get("timestamp") or "",
                    tokens=usage_to_tokens(usage),
                    effort=effort if isinstance(effort, str) else None,
                    role=role,
                    source=path.name,
                    fast=usage.get("speed") == "fast",
                )
                old = messages.get(mid)
                if old is None or found.tokens["output"] >= old.tokens["output"]:
                    if old is not None:
                        found.role, found.source = old.role, old.source
                    messages[mid] = found
    return sorted(messages.values(), key=lambda m: m.timestamp)


def window(messages: list[Message], start: str | None, until: str | None) -> list[Message]:
    lo, hi = _parse_ts(start), _parse_ts(until)
    out = []
    for m in messages:
        ts = _parse_ts(m.timestamp)
        if ts is None:
            continue
        if lo and ts <= lo:
            continue
        if hi and ts > hi:
            continue
        out.append(m)
    return out


# --------------------------------------------------------------------------- totals


@dataclass
class ModelTotals:
    model: str
    tokens: dict[str, int] = field(default_factory=lambda: dict.fromkeys(CLASSES, 0))
    cost: dict[str, float] = field(default_factory=lambda: dict.fromkeys(CLASSES, 0.0))
    requests: int = 0
    efforts: list[str] = field(default_factory=list)
    roles: set[str] = field(default_factory=set)

    @property
    def total_cost(self) -> float:
        return sum(self.cost.values())


def price_message(pricing: dict, model: str, tokens: dict[str, int], fast: bool) -> dict[str, float]:
    _, _, cfg = find_model(pricing, model)
    rates = cfg
    lc = cfg.get("long_context")
    if lc and sum(tokens[c] for c in INPUT_CLASSES) > lc["threshold_input_tokens"]:
        rates = lc["rates"]
    mult = cfg.get("fast_multiplier", 1) if fast else 1
    return {c: tokens[c] * float(rates[c]) * mult / 1_000_000 for c in CLASSES}


def add(totals: dict[str, ModelTotals], pricing: dict, model: str, tokens: dict[str, int],
        effort: str | None, role: str, requests: int = 1, fast: bool = False) -> None:
    t = totals.setdefault(model, ModelTotals(model))
    cost = price_message(pricing, model, tokens, fast)
    for c in CLASSES:
        t.tokens[c] += tokens[c]
        t.cost[c] += cost[c]
    t.requests += requests
    if effort and effort not in t.efforts:
        t.efforts.append(effort)
    t.roles.add(role)


def parse_usage_flag(text: str) -> dict:
    """Parse `model=<id>,effort=<level>,input=N,cache_write_5m=N,...,requests=N`."""
    out: dict = {"tokens": dict.fromkeys(CLASSES, 0), "requests": 1, "effort": None}
    for part in text.split(","):
        if not part.strip():
            continue
        key, _, value = part.partition("=")
        key, value = key.strip(), value.strip()
        if key == "model":
            out["model"] = value
        elif key == "effort":
            out["effort"] = value
        elif key == "requests":
            out["requests"] = int(value.replace("_", ""))
        elif key in CLASSES:
            out["tokens"][key] = int(value.replace("_", ""))
        else:
            raise ValueError(f"unknown key '{key}' in --usage")
    if "model" not in out:
        raise ValueError("--usage needs model=<id>")
    return out


# --------------------------------------------------------------------------- rendering


def fmt_tokens(n: int) -> str:
    return f"{n:,}"


def fmt_usd(x: float) -> str:
    return f"${x:,.2f}"


def usage_line(label: str, tokens: int, cost: float, hit_tokens: int, hit_cost: float) -> str:
    return (
        f"{label}: {fmt_tokens(tokens)} ({fmt_usd(cost)}) - Cache hit "
        f"({fmt_tokens(hit_tokens)}, {fmt_usd(hit_cost)})"
    )


def read_ledger(body: str) -> dict:
    matches = LEDGER_RE.findall(body or "")
    if not matches:
        return {}
    try:
        data = json.loads(matches[-1])
    except json.JSONDecodeError:
        return {}
    return data.get("sessions") or {}


def build_footer(totals: dict[str, ModelTotals], pricing: dict, *, harness: str,
                 sessions: dict[str, dict], subagents: int, source: str, note: str = "") -> str:
    if not totals:
        raise ValueError("no token usage found in the selected window")
    models = sorted(totals.values(), key=lambda t: t.total_cost, reverse=True)
    sum_tok = {c: sum(t.tokens[c] for t in models) for c in CLASSES}
    sum_cost = {c: sum(t.cost[c] for t in models) for c in CLASSES}
    in_tok = sum(sum_tok[c] for c in INPUT_CLASSES)
    in_cost = sum(sum_cost[c] for c in INPUT_CLASSES)
    hit_tok, hit_cost = sum_tok["cache_read"], sum_cost["cache_read"]
    out_tok, out_cost = sum_tok["output"], sum_cost["output"]

    names = ", ".join(
        f"{t.model} (effort {'/'.join(t.efforts) if t.efforts else 'unknown'})" for t in models
    )
    requests = sum(t.requests for t in models)
    n_sessions = len(sessions) or 1
    parts = [
        f"{requests:,} request{'s' if requests != 1 else ''}, {n_sessions} session{'s' if n_sessions != 1 else ''}, "
        + (f"{subagents} subagent{'s' if subagents != 1 else ''}" if subagents else "no subagents")
    ]
    roles = {"main": "main agent", "subagent": "subagents", "manual": "reported by flag"}
    parts.append(
        "; ".join(
            f"{t.model} ran the {' and '.join(roles[r] for r in sorted(t.roles))}" for t in models
        )
    )
    parts.append(
        f"input also holds {fmt_tokens(sum_tok['cache_write_1h'])} cache-write-1h tokens "
        f"({fmt_usd(sum_cost['cache_write_1h'])}), {fmt_tokens(sum_tok['cache_write_5m'])} "
        f"cache-write-5m ({fmt_usd(sum_cost['cache_write_5m'])}) and "
        f"{fmt_tokens(sum_tok['input'])} uncached ({fmt_usd(sum_cost['input'])})"
    )
    if len(models) > 1:
        parts.append(
            "per model: "
            + ", ".join(
                f"{t.model} {fmt_tokens(sum(t.tokens.values()))} tokens "
                f"({fmt_usd(t.total_cost)})"
                for t in models
            )
        )
    parts.append(source)
    sources = []
    for t in models:
        try:
            _, prov, _ = find_model(pricing, t.model)
        except KeyError:
            continue
        s = f"{prov['source_url']} on {prov['verified_on']}"
        if s not in sources:
            sources.append(s)
    parts.append("prices from " + ", ".join(sources) + " (USD per million tokens)")
    if note:
        parts.append(note.replace("\n", " ").strip())
    parts.append("list-price estimate, not money paid")
    metadata = "; ".join(p for p in parts if p)

    lines = [
        f"Harness Tool: {harness}",
        f"Model Name: {names}",
        usage_line("Input Token Usage", in_tok, in_cost, hit_tok, hit_cost),
        usage_line("Output Token Usage", out_tok, out_cost, 0, 0.0),
        usage_line("Total Token", in_tok + out_tok, in_cost + out_cost, hit_tok, hit_cost),
        f"Metadata: {metadata}",
    ]
    ledger = json.dumps({"v": 1, "sessions": sessions}, sort_keys=True, separators=(",", ":"))
    return "\n".join([HEADING, "", "```text", *lines, "```", f"{LEDGER_PREFIX}{ledger} -->"])


def replace_footer(body: str, footer: str) -> str:
    """Drop watermark lines and any existing footer, then append the new footer."""
    kept = [ln for ln in (body or "").splitlines() if not WATERMARK_RE.search(ln)]
    text = "\n".join(kept)
    found = list(HEADING_RE.finditer(text))
    if found:
        text = text[: found[-1].start()]
    text = text.rstrip()
    return (text + "\n\n" if text else "") + footer + "\n"


def project_dir_for(cwd: Path) -> Path:
    slug = re.sub(r"[^A-Za-z0-9]", "-", str(cwd))
    return Path.home() / ".claude" / "projects" / slug


def resolve_sessions(args) -> list[Path]:
    project = Path(args.project_dir) if args.project_dir else project_dir_for(Path.cwd())
    paths: list[Path] = []
    for s in args.session or []:
        p = Path(s)
        if not p.suffix:
            p = project / f"{s}.jsonl"
        if not p.is_file():
            raise FileNotFoundError(f"session transcript not found: {s}")
        paths.append(p)
    if not paths:
        found = sorted(project.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not found:
            raise FileNotFoundError(
                "no session transcript found; pass --session or --project-dir, or --usage for "
                "a harness without a log reader"
            )
        paths = found if args.all_sessions else found[:1]
    return paths


def prior_bodies(args) -> list[str]:
    bodies = [Path(p).read_text(encoding="utf-8") for p in args.prior_body or []]
    if args.prior_from_gh:
        out = subprocess.run(
            ["gh", "pr", "list", "--state", "all", "--limit", "100", "--json", "number,body"],
            check=True, capture_output=True, text=True,
        ).stdout
        for pr in json.loads(out):
            if args.pr and pr["number"] == args.pr:
                continue
            bodies.append(pr.get("body") or "")
    return bodies


def render(body: str, *, pricing: dict, session_paths: list[Path], manual: list[dict],
           priors: list[str], harness: str, until: str | None = None, note: str = "") -> str:
    current = read_ledger(body)
    prior_to: dict[str, str] = {}
    for pb in priors:
        for sid, entry in read_ledger(pb).items():
            to = entry.get("to")
            if to and (sid not in prior_to or _parse_ts(to) > _parse_ts(prior_to[sid])):
                prior_to[sid] = to

    totals: dict[str, ModelTotals] = {}
    ledger: dict[str, dict] = {}
    subagent_files: set[str] = set()
    spans = []
    for path in session_paths:
        sid = path.stem
        start = current[sid].get("from") if sid in current else prior_to.get(sid)
        msgs = window(read_session(path), start, until)
        if not msgs:
            continue
        for m in msgs:
            add(totals, pricing, m.model, m.tokens, m.effort, m.role, fast=m.fast)
            if m.role == "subagent":
                subagent_files.add(f"{sid}/{m.source}")
        ledger[sid] = {"from": start, "to": msgs[-1].timestamp}
        spans.append("since the previous footer" if start else "from the session start")
    for u in manual:
        add(totals, pricing, u["model"], u["tokens"], u["effort"], "manual",
            requests=u["requests"])
    if session_paths:
        span = ", ".join(sorted(set(spans))) or "no new messages"
        source = (
            f"counted from the Claude Code session JSONL (main and subagents), one count per "
            f"message id, {span}"
        )
    else:
        source = "token counts passed as flags (no log reader for this harness)"
    footer = build_footer(totals, pricing, harness=harness, sessions=ledger,
                          subagents=len(subagent_files), source=source, note=note)
    return replace_footer(body, footer)


# --------------------------------------------------------------------------- CLI


def cmd_render(args) -> int:
    body_path = Path(args.body_file)
    body = body_path.read_text(encoding="utf-8") if body_path.exists() else ""
    pricing = load_pricing(Path(args.pricing))
    manual = [parse_usage_flag(u) for u in args.usage or []]
    session_paths = [] if manual and not args.session else resolve_sessions(args)
    new = render(body, pricing=pricing, session_paths=session_paths, manual=manual,
                 priors=prior_bodies(args), harness=args.harness, until=args.until,
                 note=args.note or "")
    if args.stdout:
        sys.stdout.write(new)
    else:
        body_path.write_text(new, encoding="utf-8")
        print(f"footer written to {body_path}")
    return 0


def cmd_check_prices(args) -> int:
    path = Path(args.pricing)
    errors, warnings = check_prices(load_pricing(path))
    for w in warnings:
        print(f"WARNING {w}")
    for e in errors:
        print(f"ERROR {e}")
    if errors:
        return 1
    print(f"{path.name}: OK")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pricing", default=str(PRICING_FILE))
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("render", help="render the footer into a PR body file")
    r.add_argument("--body-file", required=True)
    r.add_argument("--harness", default=os.environ.get("AI_USAGE_HARNESS", "Claude Code"))
    r.add_argument("--session", action="append", help="session id or transcript path; repeatable")
    r.add_argument("--project-dir", help="Claude Code project log folder (default: from cwd)")
    r.add_argument("--all-sessions", action="store_true", help="every session in the project folder")
    r.add_argument("--prior-body", action="append", help="earlier PR body holding a ledger")
    r.add_argument("--prior-from-gh", action="store_true", help="read earlier PR bodies with gh")
    r.add_argument("--pr", type=int, help="this PR's number, skipped when reading earlier bodies")
    r.add_argument("--until", help="count messages up to this ISO timestamp")
    r.add_argument("--usage", action="append",
                   help="model=<id>,effort=<level>,input=N,cache_write_5m=N,cache_write_1h=N,"
                        "cache_read=N,output=N,requests=N (harness without a log reader)")
    r.add_argument("--note", help="extra free text for the Metadata line")
    r.add_argument("--stdout", action="store_true", help="print instead of writing the file")
    r.set_defaults(func=cmd_render)

    c = sub.add_parser("check-prices", help="validate the pricing file")
    c.set_defaults(func=cmd_check_prices)

    args = ap.parse_args(argv)
    try:
        return args.func(args)
    except (KeyError, ValueError, FileNotFoundError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
