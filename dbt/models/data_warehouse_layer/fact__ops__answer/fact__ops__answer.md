{% docs fact__ops__answer %}

Every answer asked through the `ask` client or the golden runner, with its automatic scores and linked cost.

## Potential Analyses

1. **Golden accuracy per day** -- share of `golden_verdict_status in ('exact_match', 'within_tolerance')` grouped by `answer_date` where `is_golden`.

## Grain

One row per `trace_id`.

## Table Lineage

```
fact__ops__answer
└── staging__langfuse__answers
    └── data_lake_layer.langfuse__answers
```

## Units and Conventions

- Timestamps (`_at`) are naive UTC; `_dt` is the real UTC day of the event, not the DAG's synthetic date.
- Money from model calls is in US dollars at list price (`_usd`), as the gateway prices it.

## Known Caveats

- Questions asked in Auto Ontology's web UI have no answer trace and are not here (PLAN 8.2).

## Refresh Cadence

Rebuilt by DAG task 8 `land_llm_telemetry` after it lands and loads the day (`dbt build --select` the ops models); the daily snapshot of task 5 carries the previous run's.

## Change History

| Version | Date | Author | Summary |
| --- | --- | --- | --- |
| 1.0.0 | 2026-11-22 | data-engineering | Initial model (M11). |

{% enddocs %}
