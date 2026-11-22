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

- **Swap by restarting only the backend.** Auto Ontology reads its model aliases from the
  environment at start, so `REASONING_MODEL`, `NON_REASONING_MODEL` and `DEFAULT_MODELS_MODEL`
  take `${AO_REASONING_MODEL:-...}` / `${AO_NON_REASONING_MODEL:-...}` (empty in `.env` means the
  defaults). `make compare-providers` recreates only `auto-ontology` (`--no-deps`) with the pair,
  checks the running container's environment, and restores the default pair in a `finally`. The
  ingestion service and catalog are untouched: no compile. Embeddings stay `adw-embed` (another
  embedding would force a full re-ingest).
- **OpenRouter ignores `chat_template_kwargs`** (new finding): `openai/adw-or-non-reasoning` with
  NVIDIA's switch still spent 148 reasoning tokens on "pong"; OpenRouter's own
  `reasoning: {enabled: false}` gives 0, like `openai/adw-non-reasoning` on NVIDIA. Both pairs
  are now the same model with the same reasoning behaviour, so the comparison is about providers.
- **The `auto-ontology` key may use the OpenRouter pair** (budgets.yaml): Auto Ontology itself makes
  the calls. The key's $2 daily budget covers both.
- **Experiments in Langfuse v4 are OTLP attributes**, not a run-items endpoint (the public API has
  none): dataset `golden` and its items (`golden-<id>`, upserted) are created over the API, and
  each comparison answer's root span carries `langfuse.experiment.{id,name,dataset.id,item.id,
  item.expected_output,item.root_observation_id}`; experiment `<run>-<candidate>`.
- **Comparison answers are not queued** for review and do not count in the daily sample (tag
  `job:compare`, not `job:chat`): they are an experiment, not the served chat.
- **Golden runner refactor:** `ask_and_score` (ask, link, score) and `answer_extra` are shared by
  `golden` and `compare`; behaviour of task 7 unchanged (tests unchanged).
- **The mart** joins answers of each run and candidate to the candidate's chat calls in the run's
  window (`fact__ops__llm_call` on the two aliases) for provider, model and p95 latency;
  `langfuse__answers` gains `finished_at`, `comparison_run`, `candidate` and both aliases, which
  went through the telemetry migration of M11 (table recreated, every day landed again).
- **Two runs, not one.** The first run favoured NVIDIA (6 vs 2 of 7), the repeat favoured
  OpenRouter (3 vs 4): the chat refuses a different set every run, so the difference between
  providers is smaller than the run-to-run spread. No swap is proposed. Latency is the one stable
  difference (p95 about 1.5 s on OpenRouter against 5.2 to 5.6 s on NVIDIA). The report says so.
- **Review on #33 (Codex): a call is linked to one answer only.** The padded windows of
  back-to-back questions overlap (2 s before, 10 s after), so a call could count for two answers;
  `owner_of` gives each call to the answer that started last before it. Counting every call of a
  run window once, the first runs cost $0.0315 / $0.0296 (run 1, nvidia / openrouter) and
  $0.0521 / $0.0100 (run 2) instead of the linked $0.0377 / $0.0388 / $0.0560 / $0.0169; the
  reports were corrected, the four mart rows of those runs keep the old linked cost. The golden
  runner's linked cost since M10 was inflated the same way.
- **Runbook test on the existing volumes** (owner's choice a): the stack was stopped (`make down`),
  the branch cloned fresh into a gitignored folder, the existing `.env` copied (the runbook's own
  instruction for a machine that already ran the stack, since volume passwords are fixed at
  creation), then the runbook followed from section 3.

## Done

- Gateway: `openai/adw-or-non-reasoning` with `chat_template_kwargs` -> 148 reasoning tokens for
  "pong"; with `reasoning: {enabled: false}` -> 0 (NVIDIA's non-reasoning alias: 0).
  `bootstrap.py keys` -> `auto-ontology` updated with the OpenRouter pair.
- `make compare-providers ALIASES=nvidia,openrouter` (run `compare-20261122T0958`, snapshot ending
  2026-01-12, 7 golden questions) -> nvidia 6 of 7 correct (85.7%), 1 refused, $0.0377, p95
  5,152 ms; openrouter 2 of 7 (28.6%), 5 refused, $0.0388, p95 1,495 ms. Every OpenRouter call
  succeeded (134 + 2 `success` in the spend log), so the refusals are the chat's, not the route's.
  Auto Ontology was back on the NVIDIA pair afterwards (container environment checked).
- Repeat (`compare-20261122T1006`) -> nvidia 3 of 7 (42.9%), 4 refused, $0.0560, p95 5,605 ms;
  openrouter 4 of 7 (57.1%), 3 refused, $0.0169, p95 1,728 ms; one verdict changed (g-0006).
  Reports: `docs/runs/compare-20261122T0958.md`, `docs/runs/compare-20261122T1006.md`.
- Airflow 2026-01-13 (`{"golden": false}`) -> task 2 recreated `langfuse__answers` (new columns),
  task 8 landed every day again (32 answers, 50 scores, 2,016 calls), ops nodes `35 success`;
  `rpt__ops__provider_comparison__snapshot` holds the four rows above, the same numbers as the
  reports. Run passed.
- Runbook from a fresh clone (`git clone -b 32-provider-comparison` into a gitignored folder,
  stack stopped first, existing `.env` copied as section 2 says): `make up-core`,
  `make backfill FROM=2026-01-01 TO=2026-01-08` -> `every day passed`; `make up-obs`,
  `make llm-smoke` -> `PASS`; `make up-ontology`, `make ontology-check` -> `PASS` (718,490,209
  equals the snapshot; 20 calls in the gateway log and Langfuse; no egress). **Done-when met**
  (on the shared volumes, as agreed). The stack was then brought back up from this worktree.
- Cost of M12's model calls: two comparisons $0.123 (every call once; $0.149 linked), checks and smoke
  under $0.01; OpenRouter's share ($0.040) is billed for real.
- `uv run pytest -q` -> PASS; every checker in `make checks` -> OK.

## Open

- No provider swap: two runs disagree. A swap proposal needs several runs per candidate (or a
  larger golden set); the mart keeps every run, so they add up.
- The comparison ran 7 golden questions; `g-0008` arrives with the label PR #30.
- Not tested: a truly empty machine (volumes created from scratch); the runbook says how.
- Knowledge: `de-0007` (OpenRouter ignores chat_template_kwargs; use `reasoning.enabled`).
