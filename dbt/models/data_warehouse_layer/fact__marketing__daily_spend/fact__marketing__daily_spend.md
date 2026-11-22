{% docs fact__marketing__daily_spend %}

Marketing spend per campaign and day, with impressions, clicks and the campaign's channel. The
marketing source writes one row for every running campaign every day. Analysts use it for spend
and efficiency by campaign and channel; `rpt__marketing__spend__daily` rolls it up per channel.

## Potential Analyses

1. **Spend against budget** -- sum `spend_idr` per `campaign_id` and join `dim__marketing__campaigns` for `budget_idr`.
2. **Click-through rate by channel** -- `sum(click_count) / nullif(sum(impression_count), 0)` grouped by `channel_name` and month of `spend_date`.
3. **Cost per click by campaign** -- `sum(spend_idr) / nullif(sum(click_count), 0)` per `campaign_id`.
4. **Spend next to revenue** -- sum `spend_idr` by `spend_date` and join `rpt__finance__revenue__daily` on `revenue_date = spend_date`; this is a same-day comparison, not attribution.

## Grain

One row per `spend_date` and `campaign_id` (test `unique_combination`).

## Table Lineage

```
fact__marketing__daily_spend
├── staging__marketing__daily_spend          (data_staging_layer)
│   └── data_lake_layer.marketing__daily_spend          (data_lake_layer)
└── staging__marketing__campaigns            (data_staging_layer)
    └── data_lake_layer.marketing__campaigns            (data_lake_layer)
```

## Units and Conventions

- `spend_idr` is whole rupiah, rounded to the thousand.
- `impression_count` and `click_count` are counts for that day.
- `channel_name` is lower case: `google`, `meta`, `tiktok` or `email`.

## Known Caveats

- Orders carry no campaign id, so spend cannot be attributed to orders; any spend-to-revenue figure is a same-period comparison.
- A day can have zero clicks for a campaign; divide with `nullif`.
- No defect in `generator/DEFECTS.md` touches marketing.

## Refresh Cadence

Rebuilt by the daily dbt build.

## Change History

| Version | Date | Author | Summary |
| --- | --- | --- | --- |
| 1.0.0 | 2026-11-22 | data-engineering | Initial doc block. |

{% enddocs %}
