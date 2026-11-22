# Golden questions

One YAML file per question, asked by the golden runner (`llm/golden.py`, DAG task 7) and
checked by `helpers/check_golden.py`. The reference SQL is written by a person and runs on the
same snapshot as the answer (`data/serve/analytics.duckdb`, read-only).

| Field | Meaning |
|---|---|
| `id` | `g-NNNN`, the file name starts with it |
| `question` | asked as written |
| `reference_sql` | one `select` (or `with`) on `data_warehouse_layer` or `data_mart_layer` |
| `kind` | `scalar`: one value; `rows`: one row per `key` value, the other columns numbers |
| `key` | for `rows`: the column that names a row |
| `tolerance_pct` | `within_tolerance` up to this relative difference (0 means exact only) |
| `needs_day` | the newest day the answer needs; skipped while the snapshot ends earlier |
| `evidence` | `da-` entries that verify any literal other than a date (rule: verify a literal) |

Scores (`infra/langfuse/scores.yaml`): `golden_verdict` is `exact_match`, `within_tolerance`,
`wrong` or `refused` (no rows); `sql_consistent` says whether the answer's own SQL reproduces its
rows. A `wrong` fails the task; `wrong`, `refused` and inconsistent answers go to the queue
`answer-review`. M11 grows this set from labels.
