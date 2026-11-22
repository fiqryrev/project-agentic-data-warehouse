# 14: M6 knowledge base (entries, kb CLI, check_knowledge, generated docs)

## Goal

PLAN section 11, row M6 (distilled knowledge in section 7): an entry format, a `kb` CLI,
generated docs, a lint with expiry and evidence, a retrieval eval, the first ten entries, and
the verify-literal skill. Done when a stale or unevidenced entry fails CI.

## Plan (as approved)

The owner pre-approved autonomous work on M5 and, if M5 was green with time left, M6, with the
plan written here instead of in chat. M6 is stacked on the M5 branch (PR #13), because both
change AGENTS.md, the Makefile and `ci.yml`.

1. Entries in `.agents/knowledge/entries/{de,da}/<id>-<slug>.md` with the PLAN frontmatter
   (`id`, `title`, `tags`, `paths`, `status`, `created`, `last_verified`, `evidence`,
   `supersedes`) and fixed body sections per kind.
2. `helpers/kb.py`: `list`, `search`, `show`, `new`, `render`.
3. `helpers/check_knowledge.py`: frontmatter, expiry, evidence resolves, generated docs current,
   retrieval recall floor; tests with bad entries.
4. First entries: `da-` for the five generator defects (with counts and their SQL), `de-` for
   decisions already in worknotes.
5. Skills `knowledge-add` and `verify-literal`; wire the check into CI, `make checks`, AGENTS.md.

## Decisions

- **Evidence is a repository file, optionally with text it must contain**
  (`"<path>::<text>"`). That resolves offline and breaks when the file or the sentence
  it rests on changes, which is what "evidence resolves" should catch. Issue and PR links are
  not accepted as evidence: checking them needs the network.
- **Expiry: `da-` 90 days, `de-` 365.** 90 matches the verify-literal rule (core rule 7);
  engineering lessons change more slowly. A warning starts 14 days before. Retired and
  superseded entries do not expire. CI checks against today's date, so the five `da-` entries
  start failing on 2027-02-21 unless re-verified. That is intended: re-verifying them is the
  `knowledge-add` skill's step 4.
- **`da-` Counts must hold a ```sql block.** Core rule 5 (every number cites its query) is
  checked for the one section that is all numbers.
- **Search is keyword scoring, no embeddings.** Title 3, tags 2.5, paths 1.5, body 1 per query
  word, with a light suffix stem; inactive entries score a quarter. It needs no network or
  model, so it runs in CI. The retrieval eval (18 questions phrased unlike the titles, recall@3,
  floor 0.9) shows whether that is enough; it scores 1.00 now. Embeddings can replace the scorer
  later behind the same eval.
- **Generated, never hand-edited:** `docs/engineering-distilled-knowledge.md`,
  `docs/data-distilled-knowledge.md`, `.agents/knowledge/index/entries.json`.
  `check_knowledge` compares them with `kb render` output.
- **The defect counts come from lake queries on the CI dataset**, recorded in each entry with
  their SQL. The rename (`shipped` to `in_transit`) needs June partitions, so it was measured on
  a scratch build of 2026-05-31 and 06-01.
- **Found while writing da-0001:** DuckDB has no `initcap`, though `generator/DEFECTS.md` gives
  `city <> initcap(city)` as the way to spot the casing defect. The entry gives a working query
  (`city = upper(city) or city = lower(city)`). DEFECTS.md is left unchanged here; see Open.
- **One day of clock slack for future dates.** CI runs in UTC; an entry written in the evening
  in UTC+7 carries tomorrow's UTC date, and the first CI run failed every entry as "in the
  future". `last_verified` may be at most one day ahead of the checker's date.
- **Codex review on PR #15:** da-0002 now says that `count(*)` counts orders only on
  `fact__sales__orders`; staging keeps one row per order state. da-0001 describes the casing
  population as every customer row written that day, with `generator/model.py` as evidence.
- **No `cold/` folder yet.** PLAN lists `.agents/knowledge/cold/` for retired entries; with ten
  active entries a `status` field is enough.

## Done

- `uv run python -m helpers.check_knowledge` → `10 entries; retrieval recall 1.00`, OK.
- `uv run python -m helpers.check_knowledge --today 2027-03-01` → five errors, one per `da-`
  entry: `stale, last verified 2026-11-22 (99 days ...)`.
- `uv run pytest -q tests/governance/test_check_knowledge.py` → 31 passed (stale, unevidenced,
  unresolvable or unquoted evidence, missing fields, bad id, status, dates, paths, supersedes,
  sections, Counts without SQL, duplicate ids, hand-edited generated doc, recall below floor,
  CLI `new`/`list`/`show`/`render`).
- Defect counts on the 3-day CI dataset (`make dbt-ci`, queries in each entry): casing 208 of
  2,088 customer rows; 12 duplicated order rows; 10 late rows of 2,532; 3 orphan lines of 2,971.
  Rename on the scratch build: 666 `shipped` rows on 05-31, 619 `in_transit` on 06-01.
- `uv run python -m helpers.check_knowledge --today 2026-11-21` (CI's UTC date) → OK.
- `uv run python -m helpers.kb search "late arriving rows"` → da-0003 first.

## Open

- Fix two lines in `generator/DEFECTS.md`: the `initcap` hint (DuckDB has no such function) and
  the casing population ("new customers"; the generator samples every customer row written that
  day, movers included, Codex review on PR #15). da-0001 holds the working query and the
  corrected population.
- "Every finished issue adds an entry or says no new lesson" is in the `knowledge-add` skill but
  not checked; `check_worknote` could require one of the two in the Open section.
- The analyst skills (explore, validate, sensemake) from the M6 row are not written yet.
- Re-verify the five `da-` entries before 2027-02-21.
- No new lesson beyond the entries above.
