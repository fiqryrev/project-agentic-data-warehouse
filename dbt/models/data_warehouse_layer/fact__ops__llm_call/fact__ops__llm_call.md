{% docs fact__ops__llm_call %}

Every model call through the gateway, one row per request (PLAN section 7: which calls, what they cost).

## Potential Analyses

1. **Cost per caller** -- `sum(spend_usd)` grouped by `call_date`, `caller_name`.
2. **Slow calls** -- `quantile_cont(call_duration_ms, 0.95)` grouped by `model_alias_name`.

## Grain

One row per `request_id`.

## Table Lineage

```
fact__ops__llm_call
└── staging__gateway__spend_logs
    └── data_lake_layer.gateway__spend_logs
```

## Units and Conventions

- Timestamps (`_at`) are naive UTC; `_dt` is the real UTC day of the event, not the DAG's synthetic date.
- Money from model calls is in US dollars at list price (`_usd`), as the gateway prices it.

## Known Caveats

- Auto Ontology's calls have no job tag and are tied to answers only by time window.

## Refresh Cadence

Rebuilt by DAG task 8 `land_llm_telemetry` after it lands and loads the day (`dbt build --select` the ops models); the daily snapshot of task 5 carries the previous run's.

## Change History

| Version | Date | Author | Summary |
| --- | --- | --- | --- |
| 1.0.0 | 2026-11-22 | data-engineering | Initial model (M11). |

{% enddocs %}
