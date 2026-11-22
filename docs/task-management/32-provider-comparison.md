# 32: M12 provider comparison and local runbook

## Goal

PLAN section 11, row M12 (section 8.6): compare model providers on the golden set before any
swap, and let a fresh clone reach a working chat from a runbook alone. Done when the comparison
table is in a PR and a fresh clone reaches a working chat from the runbook.

## Plan (as approved)

Approved in chat on 2026-11-22, with the fresh-clone test on the existing shared volumes
(option a).

1. Auto Ontology's chat aliases as compose variables (defaults unchanged); embeddings fixed.
2. Gateway alias `openai/adw-or-non-reasoning`; the `auto-ontology` key may use the OpenRouter pair.
3. `make compare-providers`: the golden set per candidate as a Langfuse experiment on dataset
   `golden`, a report in `docs/runs/`, Auto Ontology restored afterwards.
4. `rpt__ops__provider_comparison__snapshot`; `langfuse__answers` gains the candidate and end time.
5. `docs/runbook.md`, tested from a fresh clone.

## Decisions

FILL

## Done

FILL

## Open

FILL
