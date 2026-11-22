---
id: de-0008
title: Golden questions go to Auto Ontology as calculation_only
tags: [auto-ontology, refused, refusal, retrieve, information, calculation_only, golden, text-to-sql, overlay]
paths: [infra/auto-ontology/patches/0002-chat-api-calculation-only.patch, llm/ask.py, llm/golden.py]
status: active
created: 2026-11-22
last_verified: 2026-11-22
evidence:
  - "infra/auto-ontology/patches/0002-chat-api-calculation-only.patch::calculation_only: bool | None"
  - "llm/golden.py::calculation_only: bool = True"
  - docs/runs/refusals-20261122.md::tables_never_in_view
supersedes: []
---

## Rule

Ask calculation questions (the golden set, provider comparisons) with `calculation_only: true`
on Auto Ontology's chat API (overlay patch 0002). Leave it off for people in the web UI, who may
ask about the catalog itself.

## Why

Without it the text-to-SQL agent is offered `retrieve(purpose="information")`, which lists tables
briefly; a briefly listed table is not "in view", so every `run_sql` on it is refused ("Not in
view") until the 24 tool calls run out and the chat answers "I couldn't write a query". 10 of 13
refused golden answers ended that way; every answered one had used `purpose="sql"`.

## How to apply

`llm.golden.ask_and_score` sends the flag by default; `make ask` does not. To read why an answer
was refused, `uv run python -m llm.refusals` rebuilds each episode from the gateway's prompts.

## Example

NVIDIA, 7 golden questions: 5 of 21 refused over three runs without the flag, 0 with it (see
`docs/runs/refusals-20261122.md`).
