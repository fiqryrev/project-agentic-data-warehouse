{% docs fact__ops__answer_label %}

Human labels from the Langfuse queue `answer-review`, one row per answer and labeller, the five fields of the label form (PLAN 8.3) side by side. Labels drive what changes next (PLAN 8.4, `make label-prs`).

## Potential Analyses

1. **Verdict mix** -- `count(*)` grouped by `label_verdict_status`.
2. **Knowledge to write** -- rows with `label_verdict_status in ('wrong_definition', 'wrong_filter')`.

## Grain

One row per `trace_id` and `labeler_user_id`.

## Table Lineage

```
fact__ops__answer_label
└── staging__langfuse__scores
    └── data_lake_layer.langfuse__scores
```

## Units and Conventions

- Timestamps (`_at`) are naive UTC; `_dt` is the real UTC day of the event, not the DAG's synthetic date.
- Money from model calls is in US dollars at list price (`_usd`), as the gateway prices it.

## Known Caveats

- An answer from before write mode `dual` (M11) can carry a label while it is missing from `fact__ops__answer`.
- A field the labeller left empty is null.

## Refresh Cadence

Rebuilt by DAG task 8 `land_llm_telemetry` after it lands and loads the day (`dbt build --select` the ops models); the daily snapshot of task 5 carries the previous run's.

## Change History

| Version | Date | Author | Summary |
| --- | --- | --- | --- |
| 1.0.0 | 2026-11-22 | data-engineering | Initial model (M11). |

{% enddocs %}
