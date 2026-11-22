{% docs rpt__ops__pipeline_health__daily %}

Pipeline health per DAG date: status, tests, rows, refresh and golden outcome of the latest run (PLAN 8.5).

## Potential Analyses

1. **Failed days and why** -- rows where `run_status = 'failed'`.

## Grain

One row per `run_date`.

## Table Lineage

```
rpt__ops__pipeline_health__daily
└── fact__ops__pipeline_run
```

## Units and Conventions

- `run_date` is synthetic; `recorded_at` is real time.

## Known Caveats

- Lags one run (task 8 runs before record_run).

## Refresh Cadence

Rebuilt by DAG task 8 `land_llm_telemetry` after it lands and loads the day (`dbt build --select` the ops models); the daily snapshot of task 5 carries the previous run's.

## Change History

| Version | Date | Author | Summary |
| --- | --- | --- | --- |
| 1.0.0 | 2026-11-22 | data-engineering | Initial model (M11). |

{% enddocs %}
