{% docs rpt__ops__answer_quality__weekly %}

Answer quality per week: accuracy on the golden set, and the verdict mix and reasoning_ok share of human labels (PLAN 8.5).

## Potential Analyses

1. **Is the chat getting better?** -- `golden_accuracy_pct` over `week_start_date`.
2. **What kind of wrong?** -- the `label_*_count` columns of a week.

## Grain

One row per `week_start_date` (a week with answers or labels).

## Table Lineage

```
rpt__ops__answer_quality__weekly
├── fact__ops__answer
└── fact__ops__answer_label
```

## Units and Conventions

- Timestamps (`_at`) are naive UTC; `_dt` is the real UTC day of the event, not the DAG's synthetic date.
- Money from model calls is in US dollars at list price (`_usd`), as the gateway prices it.
- Answers count in the week they were asked; labels in the week they were given.

## Known Caveats

- Refusals are frequent (3 or 4 of 8 per run in M10) and count against accuracy.

## Refresh Cadence

Rebuilt by DAG task 8 `land_llm_telemetry` after it lands and loads the day (`dbt build --select` the ops models); the daily snapshot of task 5 carries the previous run's.

## Change History

| Version | Date | Author | Summary |
| --- | --- | --- | --- |
| 1.0.0 | 2026-11-22 | data-engineering | Initial model (M11). |

{% enddocs %}
