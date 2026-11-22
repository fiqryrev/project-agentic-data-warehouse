# 26: M10 ask client and golden runner: answer traces, automatic scores, DAG task 7

## Goal

PLAN section 11, row M10 (sections 8.2 and 8.3; M0 findings item 6): every answer asked through
our own `ask` client gets a full trace in Langfuse, a golden set of questions with reference SQL is
scored automatically every day, and doubtful answers go to a person. Done when a wrong golden
answer fails the task and appears in the annotation queue.

## Plan (as approved)

Approved in chat on 2026-11-22, including the real model calls (about $0.002 per answer).

1. `evals/golden/`: one YAML per question (`id`, `question`, `reference_sql`, `kind`
   scalar/rows, `key`, `tolerance_pct`, `needs_day`, `evidence`); `check_golden` in CI.
2. `llm/ask.py`: sign in through the web front door (configurable base URL for the Airflow
   containers), stream one answer, write one Langfuse answer trace; `make ask`.
3. `llm/golden.py`: ask once each, one at a time; run the reference SQL and the answer's own SQL
   read-only on the same snapshot; score `golden_verdict` and `sql_consistent`.
4. Calls linked to an answer by caller key (`auto-ontology`) and time window from the gateway's
   spend log and Langfuse generations; the trace says how it was linked.
5. `infra/langfuse/bootstrap.py` (run by `make up-obs`): score configs, the label form of PLAN 8.3
   and the queue `answer-review`; every `wrong`, `refused` or inconsistent answer is queued.
6. DAG task 7 `golden_questions` between `refresh_ontology` and `record_run`; skipped with the
   refresh or by conf; golden counts in `ops.run_log`.

## Decisions

- **Traces over OTLP (new finding, `de-0006`).** Langfuse 4.83 runs with
  `LANGFUSE_MIGRATION_V4_WRITE_MODE=events_only`: `/api/public/ingestion` refuses `trace-create`
  (400 "Event type not accepted", the first golden run lost its traces on it) and
  `GET /api/public/traces/<id>` answers 404. Traces go to `/api/public/otel/v1/traces` as OTLP JSON
  (`llm.observe.Span`, `langfuse.*` attributes, a 32-hex trace id); scores still go through
  `/ingestion`, and queue items accept the same trace id; reads use observations v2.
- **The golden runner calls no model itself.** Auto Ontology's calls carry the `auto-ontology` key
  whoever asks, so the cost lands on that key's budget ($2 per day), not on `golden-runner`'s.
  Each answer's calls are the `auto-ontology` calls in its window (start - 2 s, end + 10 s), read
  once per run from the spend log (`summarize=false`) and Langfuse generations (`toStartTime`),
  after a 20 s wait. The trace stores count, tokens, cost, request ids and generation ids, plus a
  note that web UI questions in the same window would be counted too. Generations stay separate
  traces: Langfuse cannot re-parent them.
- **Scores.** `refused` = no rows with a number (the chat ends with "couldn't write a query", no
  SQL). A scalar is matched against every number in the answer's rows (dates come as strings);
  more than 20 rows is `wrong`. `exact_match` is a difference under 0.5 for integers;
  `within_tolerance` uses `tolerance_pct`. `rows` questions match each reference row by its key,
  case-insensitively. Asked once, no retry: retries would hide the instability the queue is for.
- **The answer's SQL runs with `enable_external_access = false` and `lock_configuration`** on a
  read-only connection, interrupted after 60 s: it is model-written, so `COPY ... TO` must not
  write a file (a test proves it does not).
- **Queue:** `wrong`, `refused` and `sql_consistent = false` (PLAN 8.3). Only `wrong` fails task 7;
  `refused` is queued but passes, as PLAN 8.3 says.
- **The label form is created now** (scope moved from M11): Langfuse needs at least one score
  config to create a queue, and the form is fixed by PLAN 8.3. Queue sampling, export and marts
  stay in M11. Bootstrap creates what is missing and never edits a config (scores keep the id).
- **Airflow reaches the UI through the edge** (`AO_URL=http://ao-edge:3000`) with `Host` and
  `Origin` set to `localhost:3000`, the only origin Auto Ontology's auth trusts; checked from the
  scheduler (sign-in 200). `GATEWAY_URL` and `LANGFUSE_URL` point at the services.
- **Tasks 7 and 9 do not depend on the past.** With `depends_on_past` a wrong answer (task 7
  failed, or record_run exiting 1) would leave the next day's run waiting forever under
  `max_active_runs=1`; the data tasks 1 to 6 keep it. A wrong answer still makes the day
  `failed` in `ops.run_log` (new columns `golden_status` and counts), so the run is red.
- **Skips:** exit 99 when Auto Ontology is unreachable or the run's conf says `{"golden": false}`;
  a skipped refresh skips task 7 too. `make backfill` asks only on its last day (minutes and
  model calls per day). `GOLDEN_EXTRA_DIR` adds questions from a folder outside the repo, used
  for the deliberately wrong question below.
- **`check_golden`** (CI): fields, one read-only statement on existing `data_warehouse_layer` or
  `data_mart_layer` models, and evidence for any literal other than a date.
- **`llm/ask.py` holds the chat client**, `llm/observe.py` the gateway and Langfuse helpers;
  `ontology_check` now imports both (behaviour unchanged, `make ontology-check` passed after it).

## Done

- Stacks from this worktree: `make up-core`, `make up-obs`, `make up-ontology`, then
  `make ontology-check` -> `PASS` after the refactor: 718,490,209 for 2026-01-05,
  equal to the snapshot; 11 `auto-ontology` calls, $0.001994, 11 Langfuse generations.
- `uv run python infra/langfuse/bootstrap.py` -> 7 score configs and queue `answer-review`
  created; a second run created nothing.
- `make golden DS=2026-01-08` (first try) -> asked 7, then `Langfuse ingestion: ... "trace-create"
  is not accepted ... events_only`; traces moved to OTLP (Decisions).
- `make golden DS=2026-01-08` -> `passed: 3 exact, 0 within tolerance, 0 wrong, 4 refused;
  4 queued in answer-review; 253 linked call(s), $0.061315`. The four refusals are the chat's own
  "I couldn't write a query that answers this question" with no SQL (read back from the answer
  traces through observations v2).
- From the scheduler container: sign-in through `ao-edge` with Host `localhost:3000` -> 200;
  queue found.
- Airflow 2026-01-09 (first try): task 7 `ModuleNotFoundError: No module named 'yaml'`: the image
  installs without the dev group. PyYAML moved to the runtime dependencies (a test now checks).
- Airflow 2026-01-09 with `GOLDEN_EXTRA_DIR` (a wrong-on-purpose net revenue question) ->
  `passed`, golden `5 exact, 3 refused`, $0.057861; the deliberate question was itself refused,
  so it proved nothing.
- Airflow 2026-01-10 with the wrong-on-purpose question `g-9001` (g-0002's question, reference
  `order_count + 1`) -> `[golden] g-9001 wrong (queued): expected 666.00; answer numbers 665.00`;
  `failed: 4 exact, 0 within tolerance, 1 wrong, 3 refused; 4 queued`; $0.050704, 256 calls.
  `airflow tasks states-for-dag-run`: tasks 1 to 6 `success`, `golden_questions failed`,
  `record_run failed`. The queue `answer-review` holds trace `ddb7c260...` as `PENDING`
  (11 items in all). `ops.run_log` 2026-01-10: `failed`, `golden_status failed`, 8 asked, 1 wrong,
  3 refused, "golden questions: 1 wrong answer(s)". **Done-when met.**
- Cost: the three scored runs $0.17 (`golden.json`); the gateway log shows 707 `auto-ontology`
  calls, $0.184, since this session's stacks came up (all within the $2 daily budget). Above the
  plan's estimate: a refused answer takes 30 to 58 calls, an answered one 12 to 35.
- `uv run pytest -q` -> PASS; every checker in `make checks` (with `check_golden`) -> OK.

## Open

- **Refusals are frequent** (3 or 4 of 7 to 8 per run, a different set each time) and cost
  the most. Worth a look in M11: the labels will say whether the ontology misses a term. A retry
  is deliberately not added.
- Cost per run is about $0.05 to $0.06 (about $1.80 a month at one run a day); PLAN 8.3's
  estimate of $0.002 per answer held only for answered questions.
- The probe trace `0d31958c...` (session `probe`, one `golden_verdict` score) from testing the
  OTLP path stays in Langfuse; harmless.
- M11: daily random sample of other `ask` answers into the queue, label export (task 8),
  `ops` marts, label-to-golden and label-to-knowledge pull requests.
- Knowledge: `de-0006` (Langfuse traces over OTLP).
