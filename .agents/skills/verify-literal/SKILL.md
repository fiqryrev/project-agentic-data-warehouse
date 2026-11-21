---
name: verify-literal
description: Check that a literal value exists before filtering on it. Use before writing any WHERE col = '<literal>' (or IN, LIKE) in SQL, a dbt model, a test or an answer.
---

# verify-literal

A filter on a misspelled or retired value returns zero rows that look like a real answer.

1. Look for a `da-` entry first: `uv run python -m helpers.kb search "<table> <column>"`. An
   active entry verified within 90 days that lists the value is enough; cite its id.
2. Otherwise profile the column on the read-only connection, in the layer you will filter:
   `select <col>, count(*) from <schema>.<table> group by all order by 2 desc limit 50;`
   For history, add `min(_dt), max(_dt)` (staging) to see values that were renamed or retired.
3. Use the value exactly as profiled (case, spaces). If it is missing, stop and say so; do not
   guess a near spelling.
4. Cite the query and its result next to the filter (rule 5). A profile worth keeping becomes
   a `da-` entry (skill `knowledge-add`).

Known traps: `shipped` became `in_transit` from 2026-06-01 (da-0005); lake cities are not
all title case (da-0001).
