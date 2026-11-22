{% docs rpt__ops__llm_spend__daily %}

Model cost and tokens per day by caller, job, alias, provider and model (PLAN 8.5).

## Potential Analyses

1. **Daily spend per caller against its budget** -- `sum(spend_usd)` grouped by `call_date`, `caller_name` (budgets in infra/llm-gateway/budgets.yaml).

## Grain

One row per `call_date`, `caller_name`, `job_name`, `model_alias_name`, `provider_name`, `model_name`.

## Table Lineage

```
rpt__ops__llm_spend__daily
└── fact__ops__llm_call
```

## Units and Conventions

- Timestamps (`_at`) are naive UTC; `_dt` is the real UTC day of the event, not the DAG's synthetic date.
- Money from model calls is in US dollars at list price (`_usd`), as the gateway prices it.

## Known Caveats

- NVIDIA prices are estimates (M9).

## Refresh Cadence

Rebuilt by DAG task 8 `land_llm_telemetry` after it lands and loads the day (`dbt build --select` the ops models); the daily snapshot of task 5 carries the previous run's.

## Change History

| Version | Date | Author | Summary |
| --- | --- | --- | --- |
| 1.0.0 | 2026-11-22 | data-engineering | Initial model (M11). |

{% enddocs %}
