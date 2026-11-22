{% docs langfuse__answers %}

One row per answer trace `ask` written by the `ask` client or the golden runner (M10), landed by DAG task 8: question, answer, SQL, golden verdict and the cost of the model calls linked to it.

## Potential Analyses

1. **Golden accuracy** -- `count(*)` grouped by `golden_verdict` where `golden_id` is not null.
2. **Cost per answer** -- `avg(linked_cost_usd)` grouped by `_dt`.

## Grain

One row per `trace_id`.

## Table Lineage

```
langfuse__answers
└── data/landing-telemetry/langfuse/answers/dt=YYYY-MM-DD/part-0.parquet   (landing: written by llm/telemetry.py from GET /api/public/traces?name=ask)
```

## Units and Conventions

- Timestamps (`_at`) are naive UTC; `_dt` is the real UTC day of the event, not the DAG's synthetic date.
- Money from model calls is in US dollars at list price (`_usd`), as the gateway prices it.
- `tags` is the trace's tag list as JSON.

## Known Caveats

- Linked cost counts every `auto-ontology` call in the answer's time window; web UI questions in the same window would count too.
- Answers from before the switch to write mode `dual` (M11) are not readable and never land.

## Refresh Cadence

Landed by task 8 by trace timestamp, from the last landed day to today.

## Change History

| Version | Date | Author | Summary |
| --- | --- | --- | --- |
| 1.0.0 | 2026-11-22 | data-engineering | Initial model (M11). |

{% enddocs %}
