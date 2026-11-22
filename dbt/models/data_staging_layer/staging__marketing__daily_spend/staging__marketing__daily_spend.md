{% docs staging__marketing__daily_spend %}

Daily ad spend per campaign, `impressions` and `clicks` renamed
`impression_count` and `click_count`. Read by `fact__marketing__daily_spend`.

## Potential Analyses

1. **Spend per channel per day** -- join `staging__marketing__campaigns` on `campaign_id`, `sum(spend_idr)` by `spend_date`, `channel_name`.
2. **Click-through rate** -- `sum(click_count) / sum(impression_count)` by campaign.
3. **Cost per click** -- `sum(spend_idr) / sum(click_count)` by channel and month.

## Grain

One row per `spend_date` and `campaign_id`.

## Table Lineage

```
staging__marketing__daily_spend
└── source('lake', 'marketing__daily_spend')   (data_lake_layer)
    └── data/landing/marketing/daily_spend/dt=YYYY-MM-DD/part-0.parquet   (landing)
```

## Units and Conventions

- Money is in whole rupiah, int64, in columns ending `_idr`.
- Counts are whole numbers.
- `_dt` is the lake partition date the row arrived in.

## Known Caveats

- No generator defect touches spend (`generator/DEFECTS.md`).
- Rows are `select distinct` over the lake, so exact duplicate rows are gone.

## Refresh Cadence

View, current with the lake.

## Change History

| Version | Date | Author | Summary |
| --- | --- | --- | --- |
| 1.0.0 | 2026-11-22 | data-engineering | Initial doc block. |

{% enddocs %}
