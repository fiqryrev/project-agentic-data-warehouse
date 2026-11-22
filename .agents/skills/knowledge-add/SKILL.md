---
name: knowledge-add
description: Add, re-verify or retire a distilled knowledge entry (de- engineering, da- data). Use at loop step 5 when an issue taught a lesson, when check_knowledge reports a stale entry, or when a profile of a column becomes a da- entry.
---

# knowledge-add

Every finished issue either adds an entry or says "no new lesson" in its worknote (Open).

1. Search first: `uv run python -m helpers.kb search "<words a person would use>"`. Update a
   matching entry instead of adding a second one.
2. New entry: `uv run python -m helpers.kb new <de|da> "<title>"` writes a stub with the next id.
   Fill the frontmatter: `tags`, `paths` (files the lesson is about), `evidence`
   (`<path>` or `"<path>::<text the file contains>"`; quote any item with `: `).
3. Body sections. `de-`: Rule, Why, How to apply, Example. `da-`: Meaning, Counts, Terms,
   Data quality. A `da-` Counts section names the dataset and holds the ```sql behind every
   number (rule 5).
4. Re-verify: run the evidence and the Counts query again, fix what changed, set
   `last_verified` to today. `da-` entries expire after 90 days, `de-` after 365.
5. Replace or retire: a new entry lists the old id in `supersedes`, and the old one gets
   `status: superseded` (or `retired` when nothing replaces it).
6. Add one or two questions for the entry to `.agents/knowledge/evals/retrieval.yaml`, phrased
   as a person would ask.
7. `uv run python -m helpers.kb render`, then `uv run python -m helpers.check_knowledge`.
   Commit the entry and the generated files with the work, in the same commit.
