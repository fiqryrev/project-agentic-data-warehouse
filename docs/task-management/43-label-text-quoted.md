# 43: label text is quoted data, not instructions

## Goal

S4 of the 2026-11-23 security review. `make label-prs` copied a labeller's note and correct answer,
the question, and the chat's answer and SQL into `da-` knowledge entries (read by coding agents as
trusted knowledge) and into issues and PR bodies on a public repository: a stored
prompt-injection path, with mentions that notify people and links that are clickable.

## Plan (as approved)

Approved in chat on 2026-11-23 with phase 2 (issues #42, #43, #44):

1. One `sanitize()` for all free text from Langfuse: whitespace, length, `@` mentions, bare URLs,
   backticks and code fences.
2. In the knowledge entry, label and model text in a fenced block under a fixed line saying it is
   quoted, unverified input and not an instruction.
3. The same sentence in `AGENTS.md`.
4. `check_knowledge` fails a label `da-` entry without the block, or with instruction-like text
   outside it; fixtures in `tests/governance/`.
5. Tests: a label with a mention, a URL, a code fence and an "ignore previous instructions" line,
   neutralised in the entry, the issue body and the PR body.

## Decisions

- **Neutralise, do not delete.** `@name` becomes `(at)name`, `scheme://` becomes `scheme[:]//`,
  `www.` becomes `www[.]`, backticks become `'`, `<` and `>` become `‹` and `›`; control, zero-width
  and bidi characters are dropped; whitespace collapses to one line; a cap per field (500 for a
  note). A reviewer still reads what the labeller meant; GitHub notifies nobody and links nowhere,
  and no quoted text can close the fence it sits in. E-mail addresses lose their `@` too.
- **One line of text marks the data** (`kb.QUOTED_LINE`), shared by the writer (`llm/labels.py`)
  and the checker, so the two cannot drift. It sits right before each ```text block: Meaning (the
  question, note and correct answer) and Terms (the chat's answer and SQL).
- **The SQL stays in the Counts ```sql block** (rule 5: every number cites its query), sanitised
  and on one line, with a sentence that it is quoted and was only run read-only.
- **The title is outside every fence**, so the question goes into it only when it does not read
  like an instruction; otherwise the title is `Label <verdict>: <id>`. The checker scans the title
  too.
- **The rule applies to `da-` entries tagged `label`**, the ones `make label-prs` writes. Other
  entries are written by people in review and are not scanned; a hand-written `de-` entry may well
  say "ignore" about data.
- **Instruction-like text** (`kb.INSTRUCTION_RE`): "ignore/disregard/forget/override ...
  instructions/rules/prompt/previous/above", "system/developer prompt", "you are now", "new
  instructions", "do not tell the user". A short list on purpose: the block and the AGENTS.md
  sentence are the control; the pattern catches the obvious case in review.
- **`da-0006` migrated** to the new layout by hand: same title, numbers and SQL, its quoted text in
  the two blocks; `last_verified` unchanged (no data was re-checked).
- **PR body built by `pr_body()`** (was inline in `open_batch`) so it can be tested without GitHub.
- **Trace ids and verdicts** pass through `slug()`, so only `[a-z0-9_-]` reaches a code span or a
  file.

## Done

- `uv run pytest -q tests/pipeline/test_labels.py tests/governance/test_check_knowledge.py`: the
  hostile label (mention, URL, `www.` link, code fence, "Ignore all previous instructions", HTML,
  bidi and zero-width characters) is inert in the entry, the dbt issue body, the PR body and the
  worknote; the entry passes `check_knowledge`; fixtures fail without the block and with
  instructions in the body or title. PASS.
- `uv run python -m helpers.kb render`; `check_knowledge`: 15 entries, retrieval recall 1.00, OK.
- `uv run pytest -q`: PASS. `make checks`: PASS.

## Open

- Golden questions made from `correct` labels still copy the question verbatim into
  `evals/golden/` (it is the text asked to the chat, so sanitising would change the eval); a person
  reviews it in the batch PR. Revisit if golden files are ever read as instructions.
- Knowledge: no new lesson; the rule lives in `AGENTS.md` (Data access) and `check_knowledge`.
