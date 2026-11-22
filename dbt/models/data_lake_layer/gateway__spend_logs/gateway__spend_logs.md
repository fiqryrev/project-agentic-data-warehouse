{% docs gateway__spend_logs %}

One row per call through the LiteLLM gateway, landed from its spend log by DAG task 8 (`llm/telemetry.py`). Every model call of the project and of Auto Ontology passes the gateway, so this is the complete call record: caller key, alias, provider, status, latency, tokens and cost.

## Potential Analyses

1. **Spend per caller and day** -- `sum(spend_usd)` grouped by `_dt`, `caller_alias`.
2. **Failures** -- `count(*)` where `status = 'failure'`, grouped by `model_group`.

## Grain

One row per `request_id` (a day is re-landed whole, replacing its partition).

## Table Lineage

```
gateway__spend_logs
└── data/landing-telemetry/gateway/spend_logs/dt=YYYY-MM-DD/part-0.parquet   (landing: written by llm/telemetry.py from GET /spend/logs)
```

## Units and Conventions

- Timestamps (`_at`) are naive UTC; `_dt` is the real UTC day of the event, not the DAG's synthetic date.
- Money from model calls is in US dollars at list price (`_usd`), as the gateway prices it.
- `job_tags` is the call's tag list as JSON (`job:<name>`, `caller:<name>`, and the client's User-Agent).

## Known Caveats

- Auto Ontology cannot forward a request id; its calls are tied to an answer only by caller key and time window (M10).
- `spend_usd` for NVIDIA aliases is an estimate at the OpenRouter list price of the same model (M9).

## Refresh Cadence

Landed by task 8 for every real day from the last landed one to today; today is partial until the next run.

## Change History

| Version | Date | Author | Summary |
| --- | --- | --- | --- |
| 1.0.0 | 2026-11-22 | data-engineering | Initial model (M11). |

{% enddocs %}
