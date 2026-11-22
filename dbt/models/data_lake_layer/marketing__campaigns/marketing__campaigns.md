{% docs marketing__campaigns %}

Raw campaign catalog from the marketing source. A set of campaigns is written on
the 1st of each month (and on 2026-01-01), each running for that calendar month on one channel,
with a budget. Every other partition is empty. `staging__marketing__campaigns` reads it.

## Potential Analyses

1. **Budget per month and channel** -- `sum(budget_idr)` grouped by `start_date`, `channel`.
2. **Spend vs budget** -- join `marketing__daily_spend` on `campaign_id` and compare `sum(spend_idr)` with `budget_idr`.
3. **Channel rotation** -- `channel` by `start_date` to see which channels ran each month.

## Grain

One row per `campaign_id` (`<yyyymm> * 10 + n`).

## Table Lineage

```
marketing__campaigns
└── data/landing/marketing/campaigns/dt=YYYY-MM-DD/part-0.parquet   (landing: written by generator/, loaded by loader/)
```

## Units and Conventions

- Money is in whole rupiah, int64, in columns ending `_idr`.
- `start_date` and `end_date` are the first and last day of the month (inclusive).
- `channel` is one of `google`, `meta`, `tiktok`, `email`.
- Every row carries the loader's audit columns: `_dt` (partition date the row arrived in), `_source_file` (landing file, relative to the landing folder), `_loaded_at` (when the load ran, UTC) and `_batch_id` (`<date>-<first 12 hex of the manifest SHA-256>`).
- Column names are the source's own (no renames); staging applies the warehouse names.

## Known Caveats

- Only the first partition of a month has rows; an empty partition is normal.
- No generator defect touches this table (`generator/DEFECTS.md`).

## Refresh Cadence

Appended per daily partition by the loader; reloading a day replaces that `_dt` in one transaction.

## Change History

| Version | Date | Author | Summary |
| --- | --- | --- | --- |
| 1.0.0 | 2026-11-22 | data-engineering | Initial doc block. |

{% enddocs %}
