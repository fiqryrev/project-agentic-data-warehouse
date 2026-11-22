---
id: de-0006
title: Write Langfuse traces over OTLP, read them from observations v2
tags: [langfuse, trace, otlp, opentelemetry, ingestion, events_only, scores, annotation-queue]
paths: [llm/observe.py, llm/ask.py]
status: active
created: 2026-11-22
last_verified: 2026-11-22
evidence:
  - "llm/observe.py::LANGFUSE_MIGRATION_V4_WRITE_MODE=events_only"
  - "llm/observe.py::/api/public/otel/v1/traces"
  - docs/task-management/26-golden-runner.md::events_only
supersedes: []
---

## Rule

Send traces and spans to Langfuse 4.83 over OTLP/HTTP (`/api/public/otel/v1/traces`, JSON, header
`x-langfuse-ingestion-version: 4`); send only scores to `/api/public/ingestion`; read
observations from `/api/public/v2/observations` with a time bound.

## Why

Our Langfuse runs in `events_only` mode: `/api/public/ingestion` answers 400 "Event type not
accepted" to `trace-create` and `span-create`, and `GET /api/public/traces/<id>` answers 404. The
first golden run in M10 asked seven questions and then lost every trace on that error.

## How to apply

Build `llm.observe.Span` objects (32-hex trace id, `langfuse.trace.*` and
`langfuse.observation.*` attributes) and call `Langfuse.export_spans`. Score and queue by the
same trace id: `score-create` events and `POST /annotation-queues/<id>/items` accept it.

## Example

`llm.ask.answer_spans` gives the root span `ask` (the trace) and its child `auto-ontology chat`;
`llm.golden` then ingests `golden_verdict` and `sql_consistent` for the same trace id.
