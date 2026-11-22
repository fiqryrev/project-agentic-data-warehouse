{% docs staging__airflow__run_log %}

The latest recorded run of each DAG date, from the landed copies of `ops.run_log`.

## Potential Analyses

1. **Runs per status** -- `count(*)` grouped by `run_status`.

## Grain

One row per `run_date` (the latest `recorded_at`).

## Table Lineage

```
staging__airflow__run_log
└── data_lake_layer.airflow__run_log
```

## Units and Conventions

- `run_date` is synthetic; `recorded_at` and `_dt` are real time.

## Known Caveats

- Lags one run: task 8 runs before record_run.

## Refresh Cadence

View; reads the lake at query time.

## Change History

| Version | Date | Author | Summary |
| --- | --- | --- | --- |
| 1.0.0 | 2026-11-22 | data-engineering | Initial model (M11). |

{% enddocs %}
