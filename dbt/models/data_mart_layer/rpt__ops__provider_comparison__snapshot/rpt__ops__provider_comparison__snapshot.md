{% docs rpt__ops__provider_comparison__snapshot %}

Provider comparison on the golden set: for each run of `make compare-providers` and each candidate
provider, accuracy, cost per correct answer and p95 latency of Auto Ontology on the same snapshot
(PLAN 8.6). A provider swap is proposed only with this table (or its report from `data/runs/`, copied to `docs/runs/`) in
the pull request.

## Potential Analyses

1. **Which provider is better value?** -- `cost_per_correct_usd` and `accuracy_pct` per `candidate_name` for one `comparison_run_code`.
2. **Latency** -- `p95_latency_ms` per `candidate_name` over runs.

## Grain

One row per `comparison_run_code` and `candidate_name`.

## Table Lineage

```
rpt__ops__provider_comparison__snapshot
├── fact__ops__answer      (answers of comparison runs: verdicts, linked cost, aliases)
└── fact__ops__llm_call    (the candidate's chat calls in the run's window: latency, provider)
```

## Units and Conventions

- Money in US dollars at list price (`_usd`); latency in milliseconds (`_ms`); timestamps naive UTC.
- Accuracy counts `exact_match` and `within_tolerance`.

## Known Caveats

- Cost is linked by caller key and time window (M10); NVIDIA prices are an estimate (M9).
- p95 covers every call on the candidate's aliases in the run's window, so another caller on the same aliases at that time would count too.
- One run per candidate is weak evidence: the chat refuses a different set of questions each run (M10).

## Refresh Cadence

Rebuilt by DAG task 8 after it lands the answers of a comparison run; a snapshot of every run so far.

## Change History

| Version | Date | Author | Summary |
| --- | --- | --- | --- |
| 1.0.0 | 2026-11-22 | data-engineering | Initial model (M12). |

{% enddocs %}
