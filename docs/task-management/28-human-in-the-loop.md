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

- **Langfuse write mode `dual`** (compose). In `events_only` (Langfuse 4.83's default) every score
  read answers 404 (`/api/public/scores`, `/v2/scores`), and metrics v2 has neither TEXT scores nor
  trace ids, so labels could not be exported. `dual` also writes the legacy tables: score and trace
  reads work again (a probe score was readable after 10 s). Rows written before the switch stay
  unreadable there, so M10's golden answers never reach `fact__ops__answer`; observations v2 still
  reads them (label-prs uses it for the answer behind a label). All three profiles: 6.0 GiB of the
  7.75 GiB VM afterwards (ClickHouse 1.58 GiB).
- **Telemetry partitions are real UTC days**, not the DAG's synthetic `ds`: calls, scores and labels
  happen now. Each run lands from the last landed day (often partial) to today, through the
  project's own loader (manifest, SHA-256, audit columns), so a re-landed day replaces itself.
  Landing goes to `data/landing-telemetry/`, apart from the generator's landing.
- **Four lake tables**: `gateway__spend_logs`, `langfuse__scores`, `langfuse__answers`, and
  `airflow__run_log` (copies of `ops.run_log` rows by `recorded_at`): `ops.run_log` sits outside
  the layers, and a staging model may only read its own lake table, so pipeline health comes in
  as a source like the others. New source domain `airflow`.
- **The lake tables exist from day 1**: `load_lake` (and `make load`, `make dbt-ci`, CI) runs
  `llm.telemetry --init-only`, which creates them empty with their fixed columns (including the
  `dt` column DuckDB reads from the hive folder, as the loader's tables have it). Otherwise task 3
  would fail on a fresh file. `check_audit_columns` loads an empty telemetry day through the loader.
- **Task 8 rebuilds the ops models itself** (`--dbt`, the four staging models and everything
  downstream), since task 3 ran before the telemetry landed; the snapshot of task 5 therefore holds
  the previous run's ops marts. It runs `all_done` (a wrong golden answer is telemetry too), skips
  with exit 99 when the gateway or Langfuse is down, and writes `telemetry.json`; `record_run`
  fails a day whose landing failed or never reported (new column `telemetry_status`).
- **The quality gate ignores empty `rpt__ops__*` marts**: a fresh file or CI has no telemetry.
- **Naming:** `usd` joins the money units (model prices are US dollar list prices) and `ms` a new
  `duration` class word (latency).
- **Models (16):** staging per lake table; `fact__ops__llm_call`, `fact__ops__answer`,
  `fact__ops__answer_label` (the five label fields side by side per trace and labeller),
  `fact__ops__pipeline_run`; marts `rpt__ops__llm_spend__daily`, `rpt__ops__llm_latency__daily`,
  `rpt__ops__answer_quality__weekly` (answers by week asked, labels by week given),
  `rpt__ops__pipeline_health__daily`. `rpt__ops__provider_comparison__snapshot` is M12.
- **Daily sample:** five `ask` answers tagged `job:chat` from the last 24 hours, not yet queued,
  drawn with the run's date as seed; added at the end of task 7.
- **label-prs reads Langfuse directly**, not the warehouse: a label becomes a PR the same hour,
  not after the next DAG run. Routing per PLAN 8.4; `correct` on a golden answer is
  `already_golden`. A `da-` entry carries the labeller's note, the correct SQL run read-only on the
  snapshot (Counts), and evidence pointing at `evals/labels/processed.yaml`, which records every
  handled label so none produces two PRs. Each batch: its own issue, worktree, worknote and PR;
  the AI usage footer is rendered for the session that runs it (`--project-dir` of the calling
  checkout). `--base` lets a batch stack on an unmerged branch.
- **check_golden accepts plain `'YYYY-MM-DD'` literals** without evidence: the chat writes dates
  that way, and a golden question promoted from an answer keeps its SQL.
- **The demo labels are agent-written** (owner's default when approving): two labels through the
  API, each with the comment "Agent-written demo label (M11) ..."; their labeller is `api` and
  their source `API`. The answers were asked for the purpose with `make ask`: "What was the
  revenue on 2026-01-05?" was answered correctly (net revenue, as the mart's doc defines it), so
  it got no false label; the commission question was right and is labelled `correct`; "How many
  active customers ...?" was answered from `dim__sales__customers` validity (2,120) where an
  active customer is one who ordered that day (416): `wrong_definition`.

## Done

- Langfuse `dual`: `/api/public/scores` and `/api/public/traces` answer 200 (404 before); a
  probe TEXT score read back in 10 s (then deleted).
- `llm.telemetry` on a copy of the build file, twice -> 2026-11-22: 1,127 spend logs, 1 answer,
  1 score, 10 run log rows, the same counts on the second run (idempotent).
- `dbt build --select` the ops models on that copy -> `33 total | 33 success`.
- `make dbt-ci` with empty telemetry tables -> `Summary: 148 total | 143 success | 5 warn`.
- `make ask` x3 ($0.0015, $0.0117, $0.0055); two labels written through the API (above).
- `make label-prs` (dry run) -> `1ad14290471b correct (api) -> golden g-0008`,
  `8f4841377664 wrong_definition (api) -> knowledge da-0006`.
- `make label-prs OPEN=1 BASE=28-human-in-the-loop` -> issue #29, branch `29-labels-2026-11-22`,
  checks PASS; the footer step failed (session lookup from the batch worktree), fixed
  (`--project-dir`), the PR finished by hand with the same commands:
  https://github.com/fiqryrev/project-agentic-data-warehouse/pull/30 (`da-0006`, `g-0008`, the
  label record). Then the title and tags of `da-0006` were tightened (skill label-review, step 4).
  **First half of done-when met.**
- Airflow 2026-01-11 (`{"golden": false}`) -> every task passed; task 8 landed 1,260 calls,
  4 answers, 7 scores, 10 run log rows and built 33 ops nodes; `ops.run_log` `passed`,
  `telemetry_status passed`. `rpt__ops__answer_quality__weekly` week 2026-11-16: `label_count 2`,
  `label_correct_count 1`, `label_wrong_definition_count 1`, `reasoning_ok_share_pct 50.0`;
  `fact__ops__answer_label` holds both labels. **Second half of done-when met.**
- `uv run pytest -q` -> PASS; every checker in `make checks` -> OK.

## Open

- PR #30 (the label batch) is stacked on this branch; after this PR merges, retarget it to `main`
  if GitHub does not.
- `fact__ops__answer` starts empty for M10's answers (written before `dual`); it fills from now on.
- A label PR's `needs_day` is the newest date in its SQL; for an exclusive upper bound that is one
  day late (g-0008 says 2026-01-06). Harmless; tighten by hand when reviewing.
- M12: provider comparison and its mart.
- Knowledge: `de-0006` now covers reading scores (write mode `dual`); `da-0006` arrives through PR #30.
