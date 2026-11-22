{% docs staging__gateway__spend_logs %}

Gateway calls with warehouse names: one row per request, the job tag pulled out of the tag list.

## Potential Analyses

1. **Calls per job** -- `count(*)` grouped by `job_name`.

## Grain

One row per `request_id`; a re-landed day keeps its latest copy.

## Table Lineage

```
staging__gateway__spend_logs
└── data_lake_layer.gateway__spend_logs
```

## Units and Conventions

- Timestamps (`_at`) are naive UTC; `_dt` is the real UTC day of the event, not the DAG's synthetic date.
- Money from model calls is in US dollars at list price (`_usd`), as the gateway prices it.

## Known Caveats

- `job_name` is `none` for calls that carried no job tag (Auto Ontology's own calls).

## Refresh Cadence

View; reads the lake at query time.

## Change History

| Version | Date | Author | Summary |
| --- | --- | --- | --- |
| 1.0.0 | 2026-11-22 | data-engineering | Initial model (M11). |

{% enddocs %}
