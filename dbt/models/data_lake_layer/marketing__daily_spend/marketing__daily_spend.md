{% docs marketing__daily_spend %}

Raw daily ad spend from the marketing source: one row per running campaign per
day, with spend, impressions and clicks. Every partition has rows for the campaigns of its
month. `staging__marketing__daily_spend` reads it.

## Potential Analyses

1. **Spend per day and channel** -- join `marketing__campaigns` on `campaign_id`, `sum(spend_idr)` grouped by `spend_date`, `channel`.
2. **Click-through rate** -- `sum(clicks) / sum(impressions)` grouped by `campaign_id`.
3. **Cost per click** -- `sum(spend_idr) / sum(clicks)` grouped by channel and month.

## Grain

One row per `spend_date` and `campaign_id`.

## Table Lineage

```
marketing__daily_spend
└── data/landing/marketing/daily_spend/dt=YYYY-MM-DD/part-0.parquet   (landing: written by generator/, loaded by loader/)
```

## Units and Conventions

- Money is in whole rupiah, int64, in columns ending `_idr`.
- Spend is rounded to Rp1,000.
- `impressions` and `clicks` are counts.
- Every row carries the loader's audit columns: `_dt` (partition date the row arrived in), `_source_file` (landing file, relative to the landing folder), `_loaded_at` (when the load ran, UTC) and `_batch_id` (`<date>-<first 12 hex of the manifest SHA-256>`).
- Column names are the source's own (no renames); staging applies the warehouse names.

## Known Caveats

- Daily spend varies around budget / days in month, so a campaign can end above or below its budget.
- No generator defect touches this table (`generator/DEFECTS.md`).

## Refresh Cadence

Appended per daily partition by the loader; reloading a day replaces that `_dt` in one transaction.

## Change History

| Version | Date | Author | Summary |
| --- | --- | --- | --- |
| 1.0.0 | 2026-11-22 | data-engineering | Initial doc block. |

{% enddocs %}
