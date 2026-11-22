# 34: reduce Auto Ontology chat refusals on the golden set

## Goal

The chat refused 1 to 5 of 7 golden questions per run, a different set each time (M10 to M12),
which hid real differences (M12 could not tell providers apart). Find why, fix it through our own
configuration or an overlay patch, and show the refusal rate falls without more wrong answers.

## Plan (as approved)

Approved in chat on 2026-11-22; the second overlay patch was approved after the diagnosis showed
configuration could not fix it.

1. Diagnose every refused golden answer from the traces already stored (no model call).
2. Fix by configuration if possible; otherwise document and ask before patching.
3. Measure three runs before and three after with `make compare-providers`.

## Decisions

- **Diagnosis from the gateway's prompts** (`llm/refusals.py`, kept as a tool): Auto Ontology
  does not report how an episode ended, but each traced model call carries the whole conversation
  so far, so the longest prompt of an answer's window whose user turn is the question is its
  episode. Counts per answer: tool calls, `retrieve` purposes, validator refusals ("Not in view",
  unknown names, repeated calls), queries that ran, "No tool calls left".
- **Cause:** 10 of 13 refused answers only used `retrieve(purpose="information")`; that view lists
  tables briefly, and only a table shown in full by the sql view is "in view" for `run_sql`
  (`react/retrieve.py`, `seen_tables`). Every answered one used `purpose="sql"`. No environment
  knob changes this: the purpose parameter is offered unless the payload says `calculation_only`,
  which the chat API (`ChatRequest`) did not accept.
- **Overlay patch 0002** (approved): `calculation_only: bool | None` on `ChatRequest`, passed by
  the router through `ChatWorker.submit` and the worker queue into the agent payload; 3 files,
  69 lines. The Next.js proxy forwards the body verbatim, so the frontend is untouched. Worth
  offering upstream with 0001.
- **Who sends it:** `llm.golden.ask_and_score` (golden runner, task 7, and `compare-providers`)
  by default; `make ask` and the web UI do not, since a person may ask about the catalog.
- **Baseline:** three NVIDIA runs without the patch: M12's two NVIDIA runs plus one new run (the
  second and third new runs were stopped at the owner's word to save time; the first already made
  three).
- **Not touched:** the 3 refusals of another kind (they used the sql view); left as an Open item.

## Done

- `uv run python -m llm.refusals` on the 28 golden answers of M12's comparisons -> answered 15
  (all with `retrieve` purpose sql), refused 13: `tables_never_in_view` 5, `tool_budget_spent` 5
  (all ten with no purpose-sql retrieve), other 3.
- Baseline without the patch (NVIDIA): `compare-20261122T0958` 6 correct / 1 refused,
  `compare-20261122T1006` 3 / 4, `compare-20261122T1105` 7 / 0 -> 5 of 21 refused, 0 wrong.
- `make up-ontology` -> `applied 0001-...`, `applied 0002-chat-api-calculation-only.patch`;
  images rebuilt, no re-ingest.
- With the patch: `compare-20261122T1147` 7 correct / 0 refused ($0.0099),
  `compare-20261122T1204` 7 / 0 ($0.0110) -> 0 of 14 refused, 0 wrong. **Done-when met.**
  A third run was still going when the PR opened.
- `uv run pytest -q` -> PASS; `make checks` -> OK.

## Open

- The 3 refusals of another kind (they used the sql view, then ended early): read them with
  `llm.refusals` if they recur now that the main cause is gone.
- Offer patches 0001 and 0002 upstream.
- Knowledge: `de-0008`.
