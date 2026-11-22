# 36: link Auto Ontology's model calls to an answer by request id (overlay patch 0003)

## Goal

PLAN 8.2's next step: Auto Ontology could not forward a request id to its model clients (M0
item 6), so calls were linked to an answer by caller key and time window, which overlapping
windows proved fragile (review on #33). Make every model call of an answer carry its id.
Done when, in a golden run, every `auto-ontology` call of each answer carries that answer's tag
and every answer is linked by request id.

## Plan (as approved)

Approved in chat on 2026-11-22.

1. Overlay patch 0003: `request_id` on the chat API, kept by the worker for the question it runs;
   every model client (chat, embeddings, rerank) sends `x-litellm-tags: answer:<request_id>`.
2. The `ask` client sends the answer's trace id; `link_calls` links by the tag first, the window
   only for untagged calls; the trace says which.
3. One golden run as proof.

## Decisions

- **A module value, not a context variable** (`auto_ontology/utils/request_tags.py`): a worker
  subprocess answers one question at a time, and embeddings run on a thread pool, where a context
  variable set in the worker would not be seen. The worker sets it for every question (None when
  the caller sent none), so it never leaks into the next question.
- **Chat clients are built once and reused**, so the header cannot be a static
  `default_headers`: `ChatOpenAI` gets httpx clients whose request hook adds the current tag.
  Embeddings pass it in `extra_headers`, rerank in its own `httpx.post` headers. The id is
  checked against `^[A-Za-z0-9._:-]{1,128}$` (API field and module), so it cannot inject headers.
- **The tag is LiteLLM's own `x-litellm-tags` header**, which our callers already used for job
  tags (M8): it lands in the spend log's `request_tags` and on the Langfuse trace, with no gateway
  change. Compile and ingest calls carry no tag (no request id there).
- **Linking:** an answer with any tagged call takes exactly its tagged calls (`link_method`
  `request_id`); an answer with none (an unpatched Auto Ontology, a web UI question) falls back to
  the window, and untagged calls go only to such answers.
- **Patch extraction:** 0003 is the diff against the pinned SHA with 0001 and 0002 applied, so
  `bootstrap.sh` applies the three in order (checked from a clean reset).

## Done

- First rebuild failed: `bootstrap.sh` resets the clone with `reset --hard`, which leaves the
  untracked file a patch adds (`request_tags.py`), so 0003 met "already exists". The bootstrap now
  runs `git clean -fd` after the reset (only in the gitignored clone).
- `make up-ontology` -> `applied 0001`, `0002`, `0003`; images rebuilt, no re-ingest.
- `make compare-providers ALIASES=nvidia` (`compare-20261122T1238`) -> 6 correct, 1 wrong, 0
  refused, $0.0088. All 7 answers `link_method: request_id`, 8 to 21 calls each. In the answers'
  windows (12:39 to 12:48 UTC) the gateway logged 81 `auto-ontology` calls, every one tagged with
  its own answer; untagged calls were only outside them: 12 at 12:38:47-56 while the new
  container started (catalog warm-up, no request id), and the previous run's, from before 0003.
  **Done-when met.**
- The wrong answer is a real misreading, the kind the golden runner is for: g-0002 "How many
  orders were placed on 2026-01-03?" answered with `order_status = 'placed'` (35 instead of 665).
  Patch 0003 only adds a header.
- `uv run pytest -q` -> PASS; `make checks` -> OK.

## Open

- g-0002's `wrong_filter` (placed read as a status): label it in the queue when task 7 meets it;
  a `da-` entry ("placed" means created that day) would come from `make label-prs`.
- Offer patches 0001 to 0003 upstream.
- Knowledge: no new entry; the linking rule is in the code, the trace and this worknote.
