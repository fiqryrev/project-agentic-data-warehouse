{% docs langfuse__scores %}

One row per Langfuse score, landed by DAG task 8: the golden runner's automatic scores (`golden_verdict`, `sql_consistent`) and the human labels a person gives in the annotation queue `answer-review` (`verdict`, `reasoning_ok`, `correct_answer`, `correct_sql`, `note`).

## Potential Analyses

1. **Labels per verdict** -- `count(*)` where `name = 'verdict'`, grouped by `string_value`.
2. **Automatic vs human** -- `count(*)` grouped by `source`, `name`.

## Grain

One row per `score_id`.

## Table Lineage

```
langfuse__scores
└── data/landing-telemetry/langfuse/scores/dt=YYYY-MM-DD/part-0.parquet   (landing: written by llm/telemetry.py from GET /api/public/scores)
```

## Units and Conventions

- Timestamps (`_at`) are naive UTC; `_dt` is the real UTC day of the event, not the DAG's synthetic date.
- Money from model calls is in US dollars at list price (`_usd`), as the gateway prices it.
- `value` is numeric (categorical scores carry the category index); `string_value` holds the label or text.

## Known Caveats

- Langfuse runs in write mode `dual` since M11; scores written before the switch are not in the readable tables and never land.
- `source` is `ANNOTATION` for queue labels and `API` for scores written over the API (the golden runner, or a label written by an agent).

## Refresh Cadence

Landed by task 8 by score timestamp, from the last landed day to today.

## Change History

| Version | Date | Author | Summary |
| --- | --- | --- | --- |
| 1.0.0 | 2026-11-22 | data-engineering | Initial model (M11). |

{% enddocs %}
