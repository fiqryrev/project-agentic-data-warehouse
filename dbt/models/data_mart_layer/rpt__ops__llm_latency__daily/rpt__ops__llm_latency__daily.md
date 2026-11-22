{% docs rpt__ops__llm_latency__daily %}

Latency (p50, p95) and error rate per day and gateway alias (PLAN 8.5).

## Potential Analyses

1. **Slowest alias** -- top `p95_latency_ms` per `call_date`.

## Grain

One row per `call_date` and `model_alias_name`.

## Table Lineage

```
rpt__ops__llm_latency__daily
└── fact__ops__llm_call
```

## Units and Conventions

- Timestamps (`_at`) are naive UTC; `_dt` is the real UTC day of the event, not the DAG's synthetic date.
- Money from model calls is in US dollars at list price (`_usd`), as the gateway prices it.

## Known Caveats

- Failed calls refused by a budget take a few milliseconds and pull the median down for small aliases.

## Refresh Cadence

Rebuilt by DAG task 8 `land_llm_telemetry` after it lands and loads the day (`dbt build --select` the ops models); the daily snapshot of task 5 carries the previous run's.

## Change History

| Version | Date | Author | Summary |
| --- | --- | --- | --- |
| 1.0.0 | 2026-11-22 | data-engineering | Initial model (M11). |

{% enddocs %}
