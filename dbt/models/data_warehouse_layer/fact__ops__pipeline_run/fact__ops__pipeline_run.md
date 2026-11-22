{% docs fact__ops__pipeline_run %}

One row per DAG date: the latest recorded run of `warehouse_daily` with its tests, rows, refresh and golden outcome.

## Potential Analyses

1. **Failed days** -- rows where `run_status = 'failed'`, with `run_problem_description`.

## Grain

One row per `run_date`.

## Table Lineage

```
fact__ops__pipeline_run
└── staging__airflow__run_log
    └── data_lake_layer.airflow__run_log
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
