{% docs staging__langfuse__scores %}

Langfuse scores with warehouse names, one row per score id (latest version).

## Potential Analyses

1. **Scores per name** -- `count(*)` grouped by `score_name`, `score_source_type`.

## Grain

One row per `score_id`.

## Table Lineage

```
staging__langfuse__scores
└── data_lake_layer.langfuse__scores
```

## Units and Conventions

- Timestamps (`_at`) are naive UTC; `_dt` is the real UTC day of the event, not the DAG's synthetic date.
- Money from model calls is in US dollars at list price (`_usd`), as the gateway prices it.

## Known Caveats

- A label edited in the queue keeps its id; the latest `score_updated_at` wins.

## Refresh Cadence

View; reads the lake at query time.

## Change History

| Version | Date | Author | Summary |
| --- | --- | --- | --- |
| 1.0.0 | 2026-11-22 | data-engineering | Initial model (M11). |

{% enddocs %}
