{% docs staging__langfuse__answers %}

Answer traces with warehouse names, one row per trace.

## Potential Analyses

1. **Answers per day** -- `count(*)` grouped by `answer_started_at::date`, `is_golden`.

## Grain

One row per `trace_id`.

## Table Lineage

```
staging__langfuse__answers
└── data_lake_layer.langfuse__answers
```

## Units and Conventions

- Timestamps (`_at`) are naive UTC; `_dt` is the real UTC day of the event, not the DAG's synthetic date.
- Money from model calls is in US dollars at list price (`_usd`), as the gateway prices it.

## Known Caveats

- See the lake table: linked cost is by time window.

## Refresh Cadence

View; reads the lake at query time.

## Change History

| Version | Date | Author | Summary |
| --- | --- | --- | --- |
| 1.0.0 | 2026-11-22 | data-engineering | Initial model (M11). |

{% enddocs %}
