# 28: M11 human-in-the-loop: label export (task 8), ops marts, queue sample, label PRs

## Goal

PLAN section 11, row M11 (sections 7, 8.3 to 8.5): human labels from the Langfuse queue reach the
warehouse and change the project. Done when a labelled `wrong_definition` produces a `da-` entry
PR and the quality mart shows the label.

## Plan (as approved)

Approved in chat on 2026-11-22.

1. Langfuse write mode `dual` (score reads answer 404 in `events_only`).
2. DAG task 8 `land_llm_telemetry`: gateway spend log, Langfuse scores and answers, `ops.run_log`
   rows into the lake by real event date, idempotent per day; skipped when obs is down.
3. dbt `ops` domain: staging per table; facts for calls, answers, labels (and pipeline runs);
   marts for spend, latency, answer quality and pipeline health.
4. Queue rule: a daily random sample of five non-golden `ask` answers.
5. `make label-prs`: labels into golden questions, `da-` entries and dbt issues, as pull requests.

## Decisions

FILL

## Done

FILL

## Open

FILL
