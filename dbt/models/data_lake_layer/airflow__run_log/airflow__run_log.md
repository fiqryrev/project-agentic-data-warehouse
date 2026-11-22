{% docs airflow__run_log %}

Copies of the `ops.run_log` rows recorded each real day, landed by DAG task 8 so that pipeline health can be modelled like any other source (`ops.run_log` itself sits outside the layers).

## Potential Analyses

1. **Failed days** -- latest row per `run_date` by `recorded_at`, where `run_status = 'failed'`.

## Grain

One row per `run_date` and `recorded_at` (a rerun of a day records a new row).

## Table Lineage

```
airflow__run_log
└── data/landing-telemetry/airflow/run_log/dt=YYYY-MM-DD/part-0.parquet   (landing: written by llm/telemetry.py from ops.run_log of the build file)
```

## Units and Conventions

- `run_date` is the DAG's (synthetic) date; `_dt` is the real day the row was recorded.

## Known Caveats

- Task 8 runs before `record_run`, so a run's own row lands with the next run.

## Refresh Cadence

Landed by task 8 by `recorded_at`, from the last landed day to today.

## Change History

| Version | Date | Author | Summary |
| --- | --- | --- | --- |
| 1.0.0 | 2026-11-22 | data-engineering | Initial model (M11). |

{% enddocs %}
