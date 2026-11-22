{% docs staging__marketing__campaigns %}

Marketing campaigns, one row per campaign, `channel` renamed `channel_name`. Read
by `dim__marketing__campaigns` and `fact__marketing__daily_spend`.

## Potential Analyses

1. **Budget per channel** -- `sum(budget_idr)` grouped by `channel_name`, month of `start_date`.
2. **Campaigns running on a day** -- filter `<day> between start_date and end_date`.
3. **Spend vs budget** -- join `staging__marketing__daily_spend` on `campaign_id`.

## Grain

One row per `campaign_id`.

## Table Lineage

```
staging__marketing__campaigns
└── source('lake', 'marketing__campaigns')   (data_lake_layer)
    └── data/landing/marketing/campaigns/dt=YYYY-MM-DD/part-0.parquet   (landing)
```

## Units and Conventions

- Money is in whole rupiah, int64, in columns ending `_idr`.
- `start_date` and `end_date` are inclusive month bounds.
- `_dt` is the lake partition date the row arrived in.

## Known Caveats

- No generator defect touches campaigns (`generator/DEFECTS.md`).
- Rows are `select distinct` over the lake, so exact duplicate rows are gone.

## Refresh Cadence

View, current with the lake.

## Change History

| Version | Date | Author | Summary |
| --- | --- | --- | --- |
| 1.0.0 | 2026-11-22 | data-engineering | Initial doc block. |

{% enddocs %}
