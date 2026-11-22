{% docs rpt__marketing__spend__daily %}

Marketing spend per day and channel, with impressions, clicks and cost per click, summed over the
channel's campaigns. It is the table to read for channel spend and efficiency over time; for a
single campaign use `fact__marketing__daily_spend`.

## Potential Analyses

1. **Spend by channel per month** -- sum `spend_idr` grouped by `channel_name` and month of `spend_date`.
2. **Cost per click over a period** -- `sum(spend_idr) / nullif(sum(click_count), 0)` by `channel_name`; recompute from the sums rather than averaging `cost_per_click_idr`.
3. **Click-through rate** -- `sum(click_count) / nullif(sum(impression_count), 0)` by `channel_name`.
4. **Total spend next to revenue** -- sum `spend_idr` per `spend_date` and join `rpt__finance__revenue__daily` on `revenue_date = spend_date`.

## Grain

One row per `spend_date` and `channel_name` (test `unique_combination`).

## Table Lineage

```
rpt__marketing__spend__daily
└── fact__marketing__daily_spend               (data_warehouse_layer)
    ├── staging__marketing__daily_spend        (data_staging_layer)
    └── staging__marketing__campaigns          (data_staging_layer)
```

## Units and Conventions

- `spend_idr` and `cost_per_click_idr` are rupiah; `cost_per_click_idr` is null when there are no clicks.
- `channel_name` is lower case: `google`, `meta`, `tiktok` or `email`.

## Known Caveats

- Each month runs three of the four channels, so a channel has no rows in months it is idle; missing rows mean no campaign, not zero spend.
- `cost_per_click_idr` is a ratio per row; averaging it across days weights days equally and gives the wrong period figure.
- Orders carry no campaign id, so spend cannot be attributed to revenue.

## Refresh Cadence

Rebuilt by the daily dbt build.

## Change History

| Version | Date | Author | Summary |
| --- | --- | --- | --- |
| 1.0.0 | 2026-11-22 | data-engineering | Initial doc block. |

{% enddocs %}
